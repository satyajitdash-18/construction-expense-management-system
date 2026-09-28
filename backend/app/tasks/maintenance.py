"""Maintenance tasks for scheduled operations."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, update, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.audit_compliance import DataRetentionPolicy
from app.models.audit_event import AuditEvent
from app.models.expense import Expense
from app.models.ledger import LedgerAccount, LedgerEntry
from app.models.notification import Notification
from app.models.processing_job import ProcessingJob
from app.models.receipt import Receipt
from app.services.audit.helper import write_audit_event
from app.services.audit_compliance import create_audit_compliance_service

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def run_retention_policies(self) -> dict:
    """Run all active data retention policies."""
    return asyncio.run(_run_all_retention_policies_async())


async def _run_all_retention_policies_async() -> dict:
    """Async implementation of running all retention policies."""
    async with AsyncSessionLocal() as db:
        service = create_audit_compliance_service(db)
        return await service.run_all_retention_policies()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def cleanup_old_processing_jobs(self, days: int = 30) -> dict:
    """Clean up old processing jobs."""
    return asyncio.run(_cleanup_old_processing_jobs_async(days))


async def _cleanup_old_processing_jobs_async(days: int) -> dict:
    """Clean up old processing jobs and their attempts."""
    from app.models.processing_job import ProcessingJob, JobAttempt
    
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


@celery_app.task(bind=True, max_retries=2, default_retry_delay=3600)
def run_retention_policies(self) -> dict:
    """Run all active data retention policies."""
    return asyncio.run(_run_all_retention_policies_async())


async def _run_all_retention_policies_async() -> dict:
    """Run all active retention policies."""
    async with AsyncSessionLocal() as db:
        service = create_audit_compliance_service(db)
        return await service.run_all_retention_policies()


@celery_app.task(bind=True, max_retries=1, default_retry_delay=3600)
def generate_daily_audit_report(self) -> dict:
    """Generate daily audit report."""
    return asyncio.run(_generate_daily_audit_report_async())


async def _generate_daily_audit_report_async() -> dict:
    """Generate daily audit report."""
    from app.models.audit_event import AuditEvent
    from app.services.audit_compliance import create_audit_compliance_service
    
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


@celery_app.task
def cleanup_old_processing_jobs(days: int = 30) -> dict:
    """Clean up old processing jobs."""
    return asyncio.run(_cleanup_old_processing_jobs_async(30))


@celery_app.task
def run_all_retention_policies() -> dict:
    """Run all active retention policies."""
    return asyncio.run(_run_all_retention_policies_async())


@celery_app.task
def generate_daily_audit_report() -> dict:
    """Generate daily audit report."""
    return asyncio.run(_generate_daily_audit_report_async())


@celery_app.task
def cleanup_old_exports(days: int = 7) -> dict:
    """Clean up expired audit report exports."""
    return asyncio.run(_cleanup_old_exports_async(days))


async def _cleanup_old_exports_async(days: int) -> dict:
    """Clean up expired audit report exports."""
    from app.models.audit_compliance import AuditReportExport
    
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


@celery_app.task
def cleanup_old_processing_jobs(days: int = 30) -> dict:
    """Clean up old processing jobs."""
    return asyncio.run(_cleanup_old_processing_jobs_async(days))


@celery_app.task
def run_all_retention_policies() -> dict:
    """Run all active retention policies."""
    return asyncio.run(_run_all_retention_policies_async())


@celery_app.task
def generate_daily_audit_report() -> dict:
    """Generate daily audit report."""
    return asyncio.run(_generate_daily_audit_report_async())


@celery_app.task
def cleanup_old_exports(days: int = 7) -> dict:
    """Clean up expired audit report exports."""
    return asyncio.run(_cleanup_old_exports_async(days))


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def send_budget_alerts(self) -> dict:
    """Send budget threshold alerts."""
    return asyncio.run(_send_budget_alerts_async())


async def _send_budget_alerts_async() -> dict:
    """Send budget threshold alerts."""
    from app.models.project import Project
    from app.models.project_budget import ProjectBudget
    from app.services.budget import create_budget_service
    
    sent = 0
    errors = 0
    
    async with AsyncSessionLocal() as db:
        # Get active budgets with thresholds
        result = await db.execute(
            select(ProjectBudget).where(ProjectBudget.amount > 0)
        )
        budgets = result.scalars().all()
        
        for budget in budgets:
            try:
                service = create_budget_service(db)
                actual = await service.get_actual_spending(
                    budget.project_id,
                    budget.category_id,
                    budget.effective_from,
                    budget.effective_to,
                )
                
                if actual >= budget.amount:
                    # Budget exceeded - send alert
                    # TODO: Implement actual notification sending
                    logger.warning("Budget exceeded", 
                        project_id=budget.project_id,
                        budget_id=budget.id,
                        actual=actual,
                        budget=budget.amount
                    )
            except Exception as e:
                logger.error("Failed to check budget", budget_id=budget.id, error=str(e))
                errors += 1
        
        return {"checked": len(budgets), "alerts_sent": 0, "errors": 0}


@celery_app.task
def generate_daily_audit_report() -> dict:
    """Generate daily audit report."""
    return asyncio.run(_generate_daily_audit_report_async())


@celery_app.task
def cleanup_old_exports(days: int = 7) -> dict:
    """Clean up expired audit report exports."""
    return asyncio.run(_cleanup_old_exports_async(7))


@celery_app.task
def run_all_retention_policies() -> dict:
    """Run all active retention policies."""
    return asyncio.run(_run_all_retention_policies_async())


@celery_app.task
def cleanup_old_processing_jobs(days: int = 30) -> dict:
    """Clean up old processing jobs."""
    return asyncio.run(_cleanup_old_processing_jobs_async(30))


@celery_app.task
def cleanup_old_audit_exports(days: int = 30) -> dict:
    """Clean up old audit report exports."""
    return asyncio.run(_cleanup_old_exports_async(30))


@celery_app.task
def health_check_services() -> dict:
    """Health check for all services."""
    return asyncio.run(_health_check_services_async())


async def _health_check_services_async() -> dict:
    """Check health of all dependent services."""
    from app.core.database import AsyncSessionLocal, get_redis, get_minio
    from app.core.celery_app import celery_app
    
    results = {}
    
    # Check database
    try:
        async with AsyncSessionLocal() as db:
            await db.execute("SELECT 1")
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
        from app.core.database import get_minio
        minio = get_minio()
        minio.list_buckets()
        results["minio"] = "healthy"
    except Exception as e:
        results["minio"] = f"unhealthy: {str(e)}"
    
    # Check Celery
    try:
        from app.core.celery_app import celery_app
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        if stats:
            results["celery"] = "healthy"
        else:
            results["celery"] = "unhealthy: no workers"
    except Exception as e:
        results["celery"] = f"unhealthy: {str(e)}"
    
    return results


# Celery Beat startup task
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks after Celery app is configured."""
    # The beat schedule is defined in celery_app.conf.beat_schedule
    pass


# Task result handler
@celery_app.task(bind=True, ignore_result=True)
def task_postrun_handler(task_id, task, *args, **kwargs):
    """Handle task completion - record metrics."""
    from app.core.metrics import celery_tasks_total, celery_task_duration_seconds
    # Metrics are recorded via decorators in actual tasks
    pass


@celery_app.task(bind=True, ignore_result=True)
def task_prerun_handler(task_id, task, *args, **kwargs):
    """Handle task start - record metrics."""
    from app.core.metrics import celery_tasks_active
    from celery import current_task
    
    # Get queue from task routing
    queue = "default"
    if current_task.request.delivery_info:
        queue = current_task.request.delivery_info.get("routing_key", "default")
    
    from app.core.metrics import celery_tasks_active
    celery_tasks_active.labels(queue=queue).inc()


@celery_app.task(bind=True, ignore_result=True)
def task_postrun_handler(task_id, task, *args, **kwargs):
    """Handle task completion - record metrics."""
    from celery import current_task
    from app.core.metrics import celery_tasks_active, celery_tasks_total, celery_task_duration_seconds
    import time
    
    queue = "default"
    if current_task.request.delivery_info:
        queue = current_task.request.delivery_info.get("routing_key", "default")
    
    from app.core.metrics import celery_tasks_active
    celery_tasks_active.labels(queue=queue).dec()
    
    # Task duration would be recorded in the actual task
    pass