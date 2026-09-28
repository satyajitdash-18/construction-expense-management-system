"""Unit tests for Celery worker startup, task registration, and module integrity."""

import pytest
from app.core.celery_app import celery_app
from app.core.celery_beat_schedule import CELERY_BEAT_SCHEDULE


def test_celery_worker_module_imports():
    """Verify that all default worker task modules can be imported without error."""
    modules = celery_app.loader.import_default_modules()
    assert len(modules) >= 3
    module_names = [m.__name__ for m in modules]
    assert "app.tasks.ocr" in module_names
    assert "app.tasks.llm_extraction" in module_names
    assert "app.tasks.maintenance" in module_names


def test_celery_task_registration():
    """Verify that all scheduled and core pipeline tasks are properly registered."""
    celery_app.loader.import_default_modules()
    registered = celery_app.tasks.keys()

    # Core async pipeline tasks
    assert "app.tasks.ocr.process_ocr_task" in registered
    assert "app.tasks.llm_extraction.process_llm_extraction_task" in registered

    # Maintenance tasks
    expected_maintenance_tasks = [
        "app.tasks.maintenance.run_retention_policies",
        "app.tasks.maintenance.cleanup_old_processing_jobs",
        "app.tasks.maintenance.generate_daily_audit_report",
        "app.tasks.maintenance.cleanup_old_exports",
        "app.tasks.maintenance.send_budget_alerts",
        "app.tasks.maintenance.health_check_services",
    ]
    for task_name in expected_maintenance_tasks:
        assert task_name in registered, f"Task {task_name} must be registered in celery_app"


def test_celery_beat_schedule_tasks_exist():
    """Verify that every task referenced in beat schedule exists in celery_app.tasks."""
    celery_app.loader.import_default_modules()
    registered = celery_app.tasks.keys()

    for schedule_name, schedule_info in CELERY_BEAT_SCHEDULE.items():
        task_name = schedule_info["task"]
        assert task_name in registered, (
            f"Scheduled task '{task_name}' in '{schedule_name}' is not registered in Celery app"
        )
