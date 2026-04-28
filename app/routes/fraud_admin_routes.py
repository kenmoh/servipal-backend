from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from supabase import AsyncClient

from app.database.supabase import get_supabase_admin_client
from app.dependencies.auth import require_admin
from app.schemas.fraud_schemas import FraudLogEntry, FraudLogListResponse, FraudReviewRequest
from app.services.fraud import FraudService


router = APIRouter(prefix="/api/v1/admin/fraud", tags=["Admin Fraud"])


@router.get("/logs", response_model=FraudLogListResponse, summary="List fraud evaluations")
async def list_fraud_logs(
    event: str | None = Query(None),
    risk_level: str | None = Query(None),
    action: str | None = Query(None),
    status: str | None = Query(None),
    user_id: str | None = Query(None),
    vendor_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    _actor: dict = Depends(require_admin),
):
    service = FraudService(supabase)
    items, total = await service.list_logs(
        event=event,
        risk_level=risk_level,
        action=action,
        status_filter=status,
        user_id=user_id,
        vendor_id=vendor_id,
        limit=limit,
    )
    return FraudLogListResponse(data=items, total=total)


@router.post("/logs/{log_id}/review", response_model=FraudLogEntry, summary="Approve/Reject a fraud case")
async def review_fraud_log(
    log_id: str,
    body: FraudReviewRequest,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_admin),
):
    service = FraudService(supabase)
    return await service.review_log(
        log_id=log_id,
        reviewer_id=str(actor.get("id")),
        decision=body.decision,
        notes=body.notes,
    )
