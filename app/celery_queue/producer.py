from app.celery_queue.tasks import process_order_creation_task
from app.config.config import settings
from app.config.logging import logger


def enqueue_payment_order_creation_task(message: dict) -> str:
    if not settings.CELERY_ENABLED:
        raise RuntimeError("Celery enqueue is disabled. Set CELERY_ENABLED=true.")
    if not settings.CELERY_BROKER_URL:
        raise RuntimeError("CELERY_BROKER_URL is required for Celery enqueueing.")

    async_result = process_order_creation_task.apply_async(
        kwargs={"payload": message},
        queue=settings.CELERY_TASK_QUEUE,
        expires=settings.CELERY_TASK_EXPIRES_SECONDS,
        retry=True,
        retry_policy={
            "max_retries": settings.CELERY_PUBLISH_RETRY_MAX_RETRIES,
            "interval_start": 0,
            "interval_step": 2,
            "interval_max": 30,
        },
        delivery_mode=settings.CELERY_TASK_DEFAULT_DELIVERY_MODE,
        headers={"tx_ref": message.get("tx_ref")},
    )

    logger.info(
        "celery_order_creation_enqueued",
        tx_ref=message.get("tx_ref"),
        task_id=async_result.id,
        queue=settings.CELERY_TASK_QUEUE,
    )
    return async_result.id

def enqueue_payout_task(order_id: str, payout_to: str) -> str:
    from app.celery_queue.tasks import process_payout_task
    
    if not settings.CELERY_ENABLED:
        raise RuntimeError("Celery enqueue is disabled. Set CELERY_ENABLED=true.")
    
    async_result = process_payout_task.apply_async(
        args=[order_id, payout_to],
        queue=settings.CELERY_TASK_QUEUE,
        expires=settings.CELERY_TASK_EXPIRES_SECONDS,
        retry=True,
    )

    logger.info(
        "celery_payout_enqueued",
        order_id=order_id,
        task_id=async_result.id,
    )
    return async_result.id
