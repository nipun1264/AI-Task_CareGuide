from celery import Celery
from ..config import settings

celery_app = Celery("document_intelligence", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.task_routes = {"app.workers.tasks.*": {"queue": "documents"}}
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
