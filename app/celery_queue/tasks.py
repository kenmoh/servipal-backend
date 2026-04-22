import asyncio
from decimal import Decimal, InvalidOperation

from celery.exceptions import Ignore, MaxRetriesExceededError
from fastapi import HTTPException

from app.celery_queue.celery_app import celery_app
from app.common.order import ProcessPaymentRequest, process_payment
from app.config.config import settings
from app.config.logging import logger
from app.database.supabase import create_supabase_admin_client
from app.services.payment_idempotency import check_payment_already_processed


def normalize_payment_payload(payload: dict) -> ProcessPaymentRequest:
    tx_ref = str(payload.get("tx_ref", "")).strip()
    if not tx_ref:
        raise ValueError("payload.tx_ref is required")

    flw_ref = str(payload.get("flw_ref", "")).strip()
    if not flw_ref:
        raise ValueError("payload.flw_ref is required")

    payment_method = str(payload.get("payment_method", "")).strip().upper()
    if not payment_method:
        raise ValueError("payload.payment_method is required")

    try:
        paid_amount = float(Decimal(str(payload.get("paid_amount"))).quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError):
        raise ValueError("payload.paid_amount must be a valid number")

    if paid_amount <= 0:
        raise ValueError("payload.paid_amount must be greater than zero")

    return ProcessPaymentRequest(
        tx_ref=tx_ref,
        paid_amount=paid_amount,
        flw_ref=flw_ref,
        payment_method=payment_method,
    )

def _is_duplicate_processing_error(error: object) -> bool:
    text = str(error).lower()
    duplicate_markers = (
        "duplicate key",
        "unique constraint",
        "already processed",
        "already_processed",
    )
    return any(marker in text for marker in duplicate_markers)


def _retry_delay_seconds(current_retries: int) -> int:
    return min(
        2 ** max(1, current_retries + 1),
        settings.CELERY_TASK_RETRY_BACKOFF_MAX_SECONDS,
    )


async def _process_order_creation_async(payload: dict) -> dict:
    request_data = normalize_payment_payload(payload)
    supabase = await create_supabase_admin_client()

    try:
        already_processed, source = await check_payment_already_processed(
            supabase=supabase,
            tx_ref=request_data.tx_ref,
        )
        if already_processed:
            logger.info(
                "celery_order_creation_already_processed_precheck",
                tx_ref=request_data.tx_ref,
                source=source,
            )
            return {
                "status": "already_processed",
                "tx_ref": request_data.tx_ref,
                "source": source,
            }
        return await process_payment(data=request_data, supabase=supabase)
    finally:
        close_method = getattr(supabase, "aclose", None)
        if callable(close_method):
            await close_method()


@celery_app.task(
    bind=True,
    name="payments.process_order_creation",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
)
def process_order_creation_task(self, payload: dict) -> dict:
    tx_ref = str(payload.get("tx_ref", ""))
    try:
        result = asyncio.run(_process_order_creation_async(payload))
        logger.info(
            "celery_order_creation_processed",
            tx_ref=tx_ref,
            task_id=self.request.id,
        )
        return result

    except HTTPException as exc:
        if exc.status_code < 500:
            logger.warning(
                "celery_order_creation_non_retryable_http_error",
                tx_ref=tx_ref,
                status_code=exc.status_code,
                error=str(exc.detail),
            )
            raise Ignore()
        if _is_duplicate_processing_error(exc.detail):
            logger.info(
                "celery_order_creation_duplicate_detected_http",
                tx_ref=tx_ref,
                status_code=exc.status_code,
                error=str(exc.detail),
            )
            raise Ignore()
        delay = _retry_delay_seconds(self.request.retries)
        logger.warning(
            "celery_order_creation_retry_http_error",
            tx_ref=tx_ref,
            status_code=exc.status_code,
            retry_in_seconds=delay,
            retries=self.request.retries,
        )
        try:
            raise self.retry(exc=exc, countdown=delay)
        except MaxRetriesExceededError:
            logger.error(
                "celery_order_creation_max_retries_http_error",
                tx_ref=tx_ref,
                error=str(exc.detail),
                exc_info=True,
            )
            raise

    except ValueError as exc:
        logger.error(
            "celery_order_creation_invalid_payload",
            tx_ref=tx_ref,
            error=str(exc),
        )
        raise Ignore()

    except Exception as exc:
        if _is_duplicate_processing_error(exc):
            logger.info(
                "celery_order_creation_duplicate_detected_exception",
                tx_ref=tx_ref,
                error=str(exc),
            )
            raise Ignore()
        delay = _retry_delay_seconds(self.request.retries)
        logger.error(
            "celery_order_creation_retry_unexpected_error",
            tx_ref=tx_ref,
            retry_in_seconds=delay,
            retries=self.request.retries,
            error=str(exc),
            exc_info=True,
        )
        try:
            raise self.retry(exc=exc, countdown=delay)
        except MaxRetriesExceededError:
            logger.error(
                "celery_order_creation_max_retries_unexpected_error",
                tx_ref=tx_ref,
                error=str(exc),
                exc_info=True,
            )
            raise
