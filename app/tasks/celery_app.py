from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "leanstock",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
)
celery_app.conf.timezone = "UTC"
celery_app.conf.imports = (
    "app.tasks.decay_task",
    "app.tasks.email_task",
)
celery_app.conf.beat_schedule = {
    "dead-stock-decay-cycle": {
        "task": "app.tasks.decay_task.run_dead_stock_decay",
        "schedule": crontab(hour=2, minute=0),
    }
}
