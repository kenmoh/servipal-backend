from typing import Any, Literal
from supabase import AsyncClient
from app.celery_queue.producer import enqueue_payout_task
from app.config.config import settings
from app.config.logging import logger

def _resolve_queue_backend() -> str:
    configured = (settings.PAYMENT_QUEUE_BACKEND or "celery").strip().lower()
    if configured not in {"supabase", "celery"}:
        logger.warning(
            "invalid_payout_queue_backend_falling_back_to_celery",
            configured_backend=configured,
        )
        return "celery"
    return configured

async def _enqueue_supabase_payout_queue(
    *,
    supabase: AsyncClient,
    order_id: str,
    payout_to: str,
) -> Any:
    # If using PGMQ/Supabase as a queue
    result = await supabase.schema("pgmq_public").rpc(
        "send",
        {
            "queue_name": "payout_queue",
            "message": {
                "order_id": order_id,
                "payout_to": payout_to
            },
        }
    ).execute()
    return result.data

async def enqueue_payout_for_processing(
    *,
    supabase: AsyncClient,
    order_id: str,
    payout_to: Literal["VENDOR", "DISPATCH"],
) -> str | None:
    backend = _resolve_queue_backend()
    
    if backend == "celery":
        return enqueue_payout_task(order_id, payout_to)
    
    if backend == "supabase":
        # Placeholder for PGMQ if they decide to use it for payouts too
        return await _enqueue_supabase_payout_queue(
            supabase=supabase,
            order_id=order_id,
            payout_to=payout_to
        )
    
    return None
