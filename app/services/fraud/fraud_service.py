from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.config.logging import logger
from app.schemas.fraud_schemas import (
    FraudEvaluationEvent,
    FraudLogCreate,
    FraudLogEntry,
    RiskAction,
    RiskAssessment,
)
from app.services.fraud.risk_engine import RiskEngine, default_high_amount_threshold, utcnow
from app.services.fraud.rules import (
    rule_completion_too_fast,
    rule_high_amount,
    rule_new_account,
    rule_new_vendor,
    rule_unverified_user,
    rule_unverified_vendor,
    rule_velocity,
)


FRAUD_LOGS_TABLE = "fraud_logs"


def _client_meta(request: Request | None) -> dict[str, str | None]:
    if not request:
        return {"ip_address": None, "user_agent": None}
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return {"ip_address": ip, "user_agent": request.headers.get("user-agent")}


async def _safe_single(query) -> dict | None:
    try:
        res = await query.single().execute()
        return res.data
    except APIError:
        return None
    except Exception:
        return None


async def _safe_count(query) -> int:
    try:
        res = await query.execute()
        return int(res.count or 0)
    except Exception:
        return 0


class FraudService:
    def __init__(self, supabase: AsyncClient, *, engine: RiskEngine | None = None):
        self.supabase = supabase
        self.engine = engine or RiskEngine()

    async def evaluate(
        self,
        *,
        event: FraudEvaluationEvent,
        user_id: UUID | str | None,
        vendor_id: UUID | str | None = None,
        amount: Decimal | float | int | str | None = None,
        tx_ref: str | None = None,
        transaction_id: UUID | str | None = None,
        order_id: UUID | str | None = None,
        order_type: str | None = None,
        started_at: object = None,
        completed_at: object = None,
        request: Request | None = None,
        details: dict[str, Any] | None = None,
    ) -> RiskAssessment:
        now = utcnow()
        uid = str(user_id) if user_id else None
        vid = str(vendor_id) if vendor_id else None

        user_profile = None
        vendor_profile = None
        if uid:
            user_profile = await _safe_single(
                self.supabase.table("profiles").select("id, created_at, is_verified, user_type, metadata").eq("id", uid)
            )
        if vid:
            vendor_profile = await _safe_single(
                self.supabase.table("profiles").select("id, created_at, is_verified, user_type, metadata").eq("id", vid)
            )

        user_created_at = (user_profile or {}).get("created_at")
        vendor_created_at = (vendor_profile or {}).get("created_at")
        user_is_verified = (user_profile or {}).get("is_verified")
        vendor_is_verified = (vendor_profile or {}).get("is_verified")

        # Velocity: transaction_intents by user in the last 10 minutes (cheap and generally available).
        recent_intents = 0
        if uid:
            window_minutes = 10
            since = (now - timedelta(minutes=window_minutes)).isoformat()
            recent_intents = await _safe_count(
                self.supabase.table("transaction_intents")
                .select("id", count="exact")
                .eq("customer_id", uid)
                .gte("created_at", since)
            )
        else:
            window_minutes = 10

        # Thresholds
        user_is_new = False
        try:
            hit = rule_new_account(created_at=user_created_at, now=now)
            user_is_new = bool(hit)
        except Exception:
            user_is_new = False

        high_amount_threshold = default_high_amount_threshold(user_is_new=user_is_new)

        hits = []
        hits.append(rule_new_account(created_at=user_created_at, now=now, hours=72, weight=20))
        hits.append(rule_unverified_user(is_verified=user_is_verified, weight=15))
        if vid:
            hits.append(rule_new_vendor(created_at=vendor_created_at, now=now, days=7, weight=15))
            hits.append(rule_unverified_vendor(is_verified=vendor_is_verified, weight=15))
        hits.append(rule_high_amount(amount=amount, threshold=high_amount_threshold, weight=25))
        hits.append(rule_velocity(recent_count=recent_intents, window_minutes=window_minutes, max_allowed=3, weight=20))

        if event == FraudEvaluationEvent.SERVICE_COMPLETION:
            hits.append(
                rule_completion_too_fast(
                    started_at=started_at,
                    completed_at=completed_at,
                    min_minutes=10,
                    weight=25,
                )
            )

        assessment = self.engine.finalize(
            [h for h in hits if h is not None],
            extra_signals={
                "event": event.value,
                "tx_ref": tx_ref,
            },
        )

        await self._log_decision(
            event=event,
            user_id=uid,
            vendor_id=vid,
            amount=amount,
            tx_ref=tx_ref,
            transaction_id=str(transaction_id) if transaction_id else None,
            order_id=str(order_id) if order_id else None,
            order_type=order_type,
            assessment=assessment,
            request=request,
            details=details,
        )

        return assessment

    async def enforce(
        self,
        *,
        assessment: RiskAssessment,
        block_status_code: int = status.HTTP_403_FORBIDDEN,
        review_status_code: int = status.HTTP_409_CONFLICT,
        block_message: str = "Transaction blocked by risk controls",
        review_message: str = "Action requires manual review",
    ) -> None:
        if assessment.action == RiskAction.BLOCK:
            raise HTTPException(
                status_code=block_status_code,
                detail={"message": block_message, "risk": assessment.model_dump(mode="json")},
            )
        if assessment.action == RiskAction.REVIEW:
            raise HTTPException(
                status_code=review_status_code,
                detail={"message": review_message, "risk": assessment.model_dump(mode="json")},
            )

    async def _log_decision(
        self,
        *,
        event: FraudEvaluationEvent,
        user_id: str | None,
        vendor_id: str | None,
        amount: Decimal | float | int | str | None,
        tx_ref: str | None,
        transaction_id: str | None,
        order_id: str | None,
        order_type: str | None,
        assessment: RiskAssessment,
        request: Request | None,
        details: dict[str, Any] | None,
    ) -> None:
        meta = _client_meta(request)
        try:
            payload = FraudLogCreate(
                event=event,
                user_id=UUID(user_id) if user_id else None,
                vendor_id=UUID(vendor_id) if vendor_id else None,
                transaction_id=UUID(transaction_id) if transaction_id else None,
                order_id=UUID(order_id) if order_id else None,
                order_type=order_type,
                tx_ref=tx_ref,
                amount=float(amount) if amount is not None else None,
                risk_score=assessment.risk_score,
                risk_level=assessment.risk_level.value,
                action=assessment.action.value,
                reasons=assessment.reasons,
                ip_address=meta.get("ip_address"),
                user_agent=meta.get("user_agent"),
                status="AUTO_ALLOWED" if assessment.action == RiskAction.ALLOW else ("AUTO_BLOCKED" if assessment.action == RiskAction.BLOCK else "OPEN"),
                details=details or assessment.signals,
            )
        except Exception as e:
            logger.error("fraud_log_payload_build_failed", error=str(e))
            return

        # Logging should never break the main flow.
        try:
            await self.supabase.table(FRAUD_LOGS_TABLE).insert(payload.model_dump(mode="json", exclude_none=True)).execute()
        except Exception as e:
            logger.error("fraud_log_insert_failed", error=str(e))

    # --- Admin helpers ---
    async def list_logs(
        self,
        *,
        event: str | None = None,
        risk_level: str | None = None,
        action: str | None = None,
        status_filter: str | None = None,
        user_id: str | None = None,
        vendor_id: str | None = None,
        limit: int = 50,
    ) -> tuple[list[FraudLogEntry], int]:
        query = self.supabase.table(FRAUD_LOGS_TABLE).select("*", count="exact")
        if event:
            query = query.eq("event", event)
        if risk_level:
            query = query.eq("risk_level", risk_level)
        if action:
            query = query.eq("action", action)
        if status_filter:
            query = query.eq("status", status_filter)
        if user_id:
            query = query.eq("user_id", user_id)
        if vendor_id:
            query = query.eq("vendor_id", vendor_id)

        res = await query.order("created_at", desc=True).limit(limit).execute()
        items = [FraudLogEntry(**row) for row in (res.data or [])]
        return items, int(res.count or 0)

    async def review_log(
        self,
        *,
        log_id: str,
        reviewer_id: str,
        decision: str,
        notes: str | None = None,
    ) -> FraudLogEntry:
        now = utcnow().isoformat()
        res = (
            await self.supabase.table(FRAUD_LOGS_TABLE)
            .update(
                {
                    "status": decision,
                    "reviewed_by": reviewer_id,
                    "reviewed_at": now,
                    "review_notes": notes,
                }
            )
            .eq("id", log_id)
            .select("*")
            .single()
            .execute()
        )
        return FraudLogEntry(**res.data)

