"""Maintenance tasks for scheduled operations."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from celery.signals import task_postrun, task_prerun
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.helper import write_audit_event
from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.audit_compliance import AuditReportExport, DataRetentionPolicy
from app.models.audit_event import AuditEvent
from app.models.expense import Expense
from app.models.ledger import LedgerAccount, LedgerEntry
from app.models.notification import Notification
from app.models.processing_job import JobAttempt, ProcessingJob
from app.models.project import Project
from app.models.project_budget import ProjectBudget
from app.models.receipt import Receipt
from app.repositories.project import ProjectRepository
from app.services.audit_compliance import create_audit_compliance_service

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_retention_policies(self) -> dict:
    """Run all active data retention policies."""
    return asyncio.run(_run_all_retention_policies_async())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_all_retention_policies(self) -> dict:
    """Run all active data retention policies (alias matching beat schedule)."""
    return asyncio.run(_run_all_retention_policies_async())


async def _run_all_retention_policies_async() -> dict:
    """Async implementation of running all retention policies."""
    async with AsyncSessionLocal() as db:
        service = create_audit_compliance_service(db)
        return await service.run_all_retention_policies()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def cleanup_old_processing_jobs(self, days: int = 30) -> dict:
    """Clean up old processing jobs and attempts."""
    return asyncio.run(_cleanup_old_processing_jobs_async(days))


async def _cleanup_old_processing_jobs_async(days: int) -> dict:
    """Clean up old processing jobs and their attempts."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        # Delete old job attempts first
        old_jobs_result = await db.execute(
            select(ProcessingJob.id).where(
                ProcessingJob.created_at < cutoff,
                ProcessingJob.status.in_(["SUCCEEDED", "FAILED"]),
            )
        )
        old_job_ids = [row[0] for row in old_jobs_result]

        deleted_attempts = 0
        if old_job_ids:
            result = await db.execute(
                delete(JobAttempt).where(JobAttempt.processing_job_id.in_(old_job_ids))
            )
            deleted_attempts = result.rowcount

        # Delete old processing jobs
        result = await db.execute(
            delete(ProcessingJob).where(
                ProcessingJob.created_at < cutoff,
                ProcessingJob.status.in_(["SUCCEEDED", "FAILED"]),
            )
        )
        deleted_jobs = result.rowcount

        await db.commit()

        return {
            "deleted_jobs": deleted_jobs,
            "deleted_attempts": deleted_attempts,
        }


@celery_app.task(bind=True, max_retries=1, default_retry_delay=3600)
def generate_daily_audit_report(self) -> dict:
    """Generate daily audit report."""
    return asyncio.run(_generate_daily_audit_report_async())


async def _generate_daily_audit_report_async() -> dict:
    """Generate daily audit report."""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    async with AsyncSessionLocal() as db:
        service = create_audit_compliance_service(db)
        report_id = await service.generate_audit_report(
            report_type="daily",
            date_from=datetime.combine(yesterday, datetime.min.time()),
            date_to=datetime.combine(yesterday, datetime.max.time()),
            format="json",
            include_payload=False,
        )

        return {"report_id": str(report_id), "date": str(yesterday)}


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def cleanup_old_exports(self, days: int = 7) -> dict:
    """Clean up expired audit report exports."""
    return asyncio.run(_cleanup_old_exports_async(days))


async def _cleanup_old_exports_async(days: int) -> dict:
    """Clean up expired audit report exports."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditReportExport).where(
                AuditReportExport.expires_at < datetime.now(UTC),
            )
        )
        exports = result.scalars().all()

        deleted = 0
        for export in exports:
            try:
                import os

                if os.path.exists(export.file_path):
                    os.remove(export.file_path)
                await db.delete(export)
                deleted += 1
            except Exception as e:
                logger.error("Failed to delete export file", export_id=export.id, error=str(e))

        if deleted > 0:
            await db.commit()

        return {"deleted_exports": deleted}


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def send_budget_alerts(self) -> dict:
    """Send budget threshold alerts."""
    return asyncio.run(_send_budget_alerts_async())


async def _send_budget_alerts_async() -> dict:
    """Send budget threshold alerts by comparing project spending against budgets."""
    sent = 0
    errors = 0

    async with AsyncSessionLocal() as db:
        repo = ProjectRepository(db)
        result = await db.execute(
            select(Project.id).distinct().join(ProjectBudget, Project.id == ProjectBudget.project_id)
        )
        project_ids = result.scalars().all()

        for project_id in project_ids:
            try:
                bva = await repo.get_budget_vs_actual(project_id)
                total_budget = bva.get("total_budget", 0)
                total_actual = bva.get("total_actual", 0)

                if total_budget > 0 and total_actual >= total_budget:
                    logger.warning(
                        "Budget threshold exceeded",
                        project_id=str(project_id),
                        total_budget=total_budget,
                        total_actual=total_actual,
                    )
                    sent += 1
            except Exception as e:
                logger.error("Failed to check budget", project_id=str(project_id), error=str(e))
                errors += 1

        return {"checked": len(project_ids), "alerts_sent": sent, "errors": errors}


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def health_check_services(self) -> dict:
    """Health check for all services."""
    return asyncio.run(_health_check_services_async())


async def _health_check_services_async() -> dict:
    """Check health of all dependent services."""
    from app.core.celery_app import celery_app
    from app.core.database import AsyncSessionLocal, get_minio, get_redis

    results = {}

    # Check database
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        results["database"] = "healthy"
    except Exception as e:
        results["database"] = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        redis = await get_redis()
        await redis.ping()
        results["redis"] = "healthy"
    except Exception as e:
        results["redis"] = f"unhealthy: {str(e)}"

    # Check MinIO
    try:
        minio = get_minio()
        minio.list_buckets()
        results["minio"] = "healthy"
    except Exception as e:
        results["minio"] = f"unhealthy: {str(e)}"

    # Check Celery
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats() if inspect else None
        if stats:
            results["celery"] = "healthy"
        else:
            results["celery"] = "unhealthy: no workers"
    except Exception as e:
        results["celery"] = f"unhealthy: {str(e)}"

    return results


# Celery Beat startup hook
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks after Celery app is configured."""
    pass


# Celery metric signal handlers
@task_prerun.connect
def task_prerun_handler(task_id=None, task=None, *args, **kwargs):
    """Handle task start - record metrics."""
    try:
        from celery import current_task

        from app.core.metrics import celery_tasks_active

        queue = "default"
        if current_task and getattr(current_task, "request", None) and current_task.request.delivery_info:
            queue = current_task.request.delivery_info.get("routing_key", "default")

        celery_tasks_active.labels(queue=queue).inc()
    except Exception:
        pass


@task_postrun.connect
def task_postrun_handler(task_id=None, task=None, *args, **kwargs):
    """Handle task completion - record metrics."""
    try:
        from celery import current_task

        from app.core.metrics import celery_tasks_active

        queue = "default"
        if current_task and getattr(current_task, "request", None) and current_task.request.delivery_info:
            queue = current_task.request.delivery_info.get("routing_key", "default")

        celery_tasks_active.labels(queue=queue).dec()
    except Exception:
        pass