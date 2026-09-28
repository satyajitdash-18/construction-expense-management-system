"""Celery Beat schedule configuration for periodic tasks."""

from celery.schedules import crontab

# Celery Beat Schedule Configuration
CELERY_BEAT_SCHEDULE = {
    # Data retention policies - run daily at 2 AM
    'run-retention-policies': {
        'task': 'app.tasks.maintenance.run_retention_policies',
        'schedule': crontab(hour=2, minute=0),
        'options': {'queue': 'maintenance'},
    },

    # Generate daily audit report at 1 AM
    'generate-daily-audit-report': {
        'task': 'app.tasks.maintenance.generate_daily_audit_report',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': 'maintenance'},
    },

    # Run all retention policies weekly on Sunday at 4 AM
    'run-all-retention-policies': {
        'task': 'app.tasks.maintenance.run_all_retention_policies',
        'schedule': crontab(hour=4, minute=0, day_of_week=0),
        'options': {'queue': 'maintenance'},
    },

    # Cleanup old processing jobs - daily at 5 AM
    'cleanup-old-jobs': {
        'task': 'app.tasks.maintenance.cleanup_old_processing_jobs',
        'schedule': crontab(hour=5, minute=0),
        'options': {'queue': 'maintenance'},
    },

    # Send budget alerts daily at 7 AM
    'send-budget-alerts': {
        'task': 'app.tasks.maintenance.send_budget_alerts',
        'schedule': crontab(hour=7, minute=0),
        'options': {'queue': 'maintenance'},
    },

    # Cleanup old audit report exports - weekly on Sunday at 5 AM
    'cleanup-old-exports': {
        'task': 'app.tasks.maintenance.cleanup_old_exports',
        'schedule': crontab(hour=5, minute=0, day_of_week=0),
        'options': {'queue': 'maintenance'},
    },

    # Health check for all services - every 5 minutes
    'health-check-services': {
        'task': 'app.tasks.maintenance.health_check_services',
        'schedule': crontab(minute='*/5'),
        'options': {'queue': 'maintenance'},
    },
}

# Celery Beat settings
CELERY_BEAT_SETTINGS = {
    'CELERY_BEAT_SCHEDULER': 'celery.beat.PersistentScheduler',
    'CELERY_BEAT_SCHEDULE_FILENAME': '/data/celerybeat-schedule',
    'CELERY_BEAT_MAX_LOOP_INTERVAL': 300,  # 5 minutes
    'CELERY_BEAT_SYNC_EVERY': 10,
}

# Task routing configuration
CELERY_TASK_ROUTES = {
    'app.tasks.ocr.*': {'queue': 'ocr'},
    'app.tasks.llm_extraction.*': {'queue': 'extraction'},
    'app.tasks.maintenance.*': {'queue': 'maintenance'},
}

# Task default settings
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_DEFAULT_EXCHANGE = 'default'
CELERY_TASK_DEFAULT_EXCHANGE_TYPE = 'direct'
CELERY_TASK_DEFAULT_ROUTING_KEY = 'default'

# Task serialization
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Result backend settings
CELERY_RESULT_BACKEND = 'redis://redis:6379/1'
CELERY_RESULT_EXTENDED = True
CELERY_RESULT_EXPIRES = 86400  # 24 hours

# Task execution settings
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 3600  # 1 hour
CELERY_TASK_SOFT_TIME_LIMIT = 3000  # 50 minutes

# Worker settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 500000  # 500MB

# Beat settings
CELERY_BEAT_SCHEDULER = 'celery.beat.PersistentScheduler'
CELERY_BEAT_SCHEDULE_FILENAME = '/data/celerybeat-schedule'
CELERY_BEAT_MAX_LOOP_INTERVAL = 300