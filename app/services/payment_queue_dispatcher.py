from typing import Any

from supabase import AsyncClient

from app.celery_queue.producer import enqueue_payment_order_creation_task
from app.config.config import settings
from app.config.logging import logger


def _build_message(
    *,
    tx_ref: str,
    paid_amount: Any,
    flw_ref: Any,
    payment_type: Any,
    tx_id: Any,
) -> dict:
    return {
        "tx_ref": tx_ref,
        "paid_amount": str(paid_amount),
        "flw_ref": str(flw_ref),
        "payment_method": f"{(payment_type or '').upper()}",
        "tx_id": tx_id,
    }


def _resolve_queue_backend() -> str:
    configured = (settings.PAYMENT_QUEUE_BACKEND or "supabase").strip().lower()
    if configured not in {"supabase", "dual", "celery"}:
        logger.warning(
            "invalid_payment_queue_backend_falling_back_to_supabase",
            configured_backend=configured,
        )
        return "supabase"
    return configured


async def _enqueue_supabase_payment_queue(
    *,
    supabase: AsyncClient,
    message: dict,
) -> int | None:
    result = (
        await supabase.schema("pgmq_public")
        .rpc(
            "send",
            {
                "queue_name": "payment_queue",
                "message": message,
            },
        )
        .execute()
    )
    return result.data


async def enqueue_successful_payment_for_processing(
    *,
    supabase: AsyncClient,
    tx_ref: str,
    paid_amount: Any,
    flw_ref: Any,
    payment_type: Any,
    tx_id: Any,
) -> dict:
    backend = _resolve_queue_backend()
    message = _build_message(
        tx_ref=tx_ref,
        paid_amount=paid_amount,
        flw_ref=flw_ref,
        payment_type=payment_type,
        tx_id=tx_id,
    )

    dispatch_result = {
        "backend": backend,
        "supabase_msg_id": None,
        "celery_task_id": None,
    }
    failed_backends: list[str] = []

    if backend in {"supabase", "dual"}:
        try:
            dispatch_result["supabase_msg_id"] = await _enqueue_supabase_payment_queue(
                supabase=supabase,
                message=message,
            )
        except Exception as exc:
            logger.error(
                "payment_queue_supabase_enqueue_failed",
                tx_ref=tx_ref,
                error=str(exc),
                exc_info=True,
            )
            if backend == "supabase":
                raise
            failed_backends.append("supabase")

    if backend in {"celery", "dual"}:
        try:
            dispatch_result["celery_task_id"] = enqueue_payment_order_creation_task(
                message
            )
        except Exception as exc:
            logger.error(
                "payment_queue_celery_enqueue_failed",
                tx_ref=tx_ref,
                error=str(exc),
                exc_info=True,
            )
            if backend == "celery":
                raise
            failed_backends.append("celery")

    if not dispatch_result["supabase_msg_id"] and not dispatch_result["celery_task_id"]:
        raise RuntimeError(
            "Unable to enqueue payment processing message in any configured backend."
        )

    if failed_backends:
        logger.warning(
            "payment_queue_partial_enqueue",
            tx_ref=tx_ref,
            backend=backend,
            failed_backends=failed_backends,
            supabase_msg_id=dispatch_result["supabase_msg_id"],
            celery_task_id=dispatch_result["celery_task_id"],
        )

    return dispatch_result
