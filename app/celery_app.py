from celery import Celery
from app.config import settings

celery = Celery(
    "transaction_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

celery.conf.task_default_queue = "default"
celery.conf.task_routes = {
    "app.tasks.process_job": {"queue": "default"}
}