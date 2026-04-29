import ssl
from urllib.parse import urlsplit
from celery import Celery
from kombu import Queue

from app.config.config import settings


def _resolve_ssl_cert_reqs(value: str) -> int:
    normalized = (value or "required").strip().lower()
    mapping = {
        "required": ssl.CERT_REQUIRED,
        "optional": ssl.CERT_OPTIONAL,
        "none": ssl.CERT_NONE,
    }
    return mapping.get(normalized, ssl.CERT_REQUIRED)


def _redis_ssl_options() -> dict | None:
    if not settings.CELERY_REDIS_USE_SSL:
        return None
    return {
        "ssl_cert_reqs": _resolve_ssl_cert_reqs(settings.CELERY_REDIS_SSL_CERT_REQS)
    }


broker_url = settings.CELERY_BROKER_URL or "memory://"
result_backend = settings.CELERY_RESULT_BACKEND or "cache+memory://"
broker_scheme = (urlsplit(broker_url).scheme or "").lower()
is_redis_broker = broker_scheme.startswith("redis")
is_rabbitmq_broker = broker_scheme in {"amqp", "amqps", "pyamqp"}

queue_arguments = None
if is_rabbitmq_broker and settings.CELERY_RABBITMQ_QUEUE_TYPE:
    queue_arguments = {"x-queue-type": settings.CELERY_RABBITMQ_QUEUE_TYPE}

broker_transport_options = {}
if is_redis_broker:
    broker_transport_options["visibility_timeout"] = (
        settings.CELERY_BROKER_VISIBILITY_TIMEOUT_SECONDS
    )
if is_rabbitmq_broker:
    broker_transport_options["confirm_publish"] = True

celery_app = Celery(
    "servipal_payments",
    broker=broker_url,
    backend=result_backend,
    include=["app.celery_queue.tasks"],
)

celery_app.conf.update(
    task_default_queue=settings.CELERY_TASK_QUEUE,
    task_default_exchange=settings.CELERY_TASK_QUEUE,
    task_default_exchange_type="direct",
    task_default_routing_key=settings.CELERY_TASK_QUEUE,
    task_default_delivery_mode=settings.CELERY_TASK_DEFAULT_DELIVERY_MODE,
    task_routes={
        "payments.process_order_creation": {
            "queue": settings.CELERY_TASK_QUEUE,
            "routing_key": settings.CELERY_TASK_QUEUE,
        },
        "payments.process_payout": {
            "queue": settings.CELERY_TASK_QUEUE,
            "routing_key": settings.CELERY_TASK_QUEUE,
        }
    },
    broker_transport_options=broker_transport_options,
    task_queues=(
        Queue(
            settings.CELERY_TASK_QUEUE,
            durable=True,
            routing_key=settings.CELERY_TASK_QUEUE,
            queue_arguments=queue_arguments,
        ),
    ),
    task_create_missing_queues=False,
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_ignore_result=settings.CELERY_TASK_IGNORE_RESULT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SECONDS,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
    result_expires=settings.CELERY_TASK_EXPIRES_SECONDS,
    worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
    worker_max_tasks_per_child=settings.CELERY_WORKER_MAX_TASKS_PER_CHILD,
    worker_max_memory_per_child=settings.CELERY_WORKER_MAX_MEMORY_PER_CHILD_KB,
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
    broker_connection_retry_on_startup=True,
    broker_heartbeat=settings.CELERY_BROKER_HEARTBEAT,
    broker_connection_timeout=settings.CELERY_BROKER_CONNECTION_TIMEOUT_SECONDS,
    broker_pool_limit=settings.CELERY_BROKER_POOL_LIMIT,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": settings.CELERY_PUBLISH_RETRY_MAX_RETRIES,
        "interval_start": 0,
        "interval_step": 2,
        "interval_max": 30,
    },
)

redis_ssl_options = _redis_ssl_options()
if redis_ssl_options and is_redis_broker:
    celery_app.conf.broker_use_ssl = redis_ssl_options
    celery_app.conf.redis_backend_use_ssl = redis_ssl_options
