"""Celery app configuration."""

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import settings
from app.core.celery_beat_schedule import CELERY_BEAT_SCHEDULE, CELERY_TASK_ROUTES

celery_app = Celery(
    "construction_expense",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.ocr",
        "app.tasks.llm_extraction",
        "app.tasks.maintenance",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Result backend
    result_extended=True,
    result_expires=86400,
    
    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    
    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=500000,
    
    # Beat schedule
    beat_schedule=CELERY_BEAT_SCHEDULE,
    beat_scheduler="celery.beat.PersistentScheduler",
    beat_schedule_filename="/data/celerybeat-schedule",
    beat_max_loop_interval=300,
    
    # Task routing and queues
    task_routes=CELERY_TASK_ROUTES,
    task_queues=[
        Queue("default"),
        Queue("ocr"),
        Queue("extraction"),
        Queue("maintenance"),
    ],
    
    # Default queue settings
    task_default_queue="default",
    task_default_exchange="default",
    task_default_exchange_type="direct",
    task_default_routing_key="default",
)

from celery.signals import task_postrun, worker_process_init


@worker_process_init.connect
def on_worker_process_init(**kwargs: object) -> None:
    """Ensure child worker process does not inherit parent event loop connections."""
    try:
        from app.core.database import engine
        engine.sync_engine.dispose()
    except Exception:
        pass


@task_postrun.connect
def on_task_postrun(**kwargs: object) -> None:
    """Dispose connection pool between tasks so new asyncio.run loops get clean connections."""
    try:
        from app.core.database import engine
        engine.sync_engine.dispose()
    except Exception:
        pass