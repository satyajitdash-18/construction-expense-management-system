"""OCR Celery tasks."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import Celery
from sqlalchemy import delete, select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.enums import JobStatus, JobType
from app.models.evidence import Evidence
from app.models.expense import Expense
from app.models.processing_job import JobAttempt, ProcessingJob
from app.services.ocr import create_ocr_service
from app.services.storage import create_storage_service

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_ocr_task(task_self: Celery, job_id: str, evidence_id: str | None = None) -> dict:
    """
    Process OCR on evidence file.

    Args:
        job_id: ProcessingJob ID
        evidence_id: Optional Evidence ID (for direct evidence processing)

    Returns:
        OCR result dict
    """
    return asyncio.run(_process_ocr_async(task_self, job_id, evidence_id))


async def _process_ocr_async(
    task_self: Celery,
    job_id: str,
    evidence_id: str | None = None,
) -> dict:
    """Async OCR processing logic."""
    job_uuid = UUID(job_id)
    evidence_uuid = UUID(evidence_id) if evidence_id else None

    async with AsyncSessionLocal() as db:
        # Retrieve the specific processing job passed by caller
        job = await db.get(ProcessingJob, job_uuid)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Resolve evidence
        evidence = None
        if evidence_uuid:
            evidence = await db.get(Evidence, evidence_uuid)
        elif job.source_event_id:
            exp_result = await db.execute(
                select(Expense).where(Expense.source_event_id == job.source_event_id)
            )
            exp = exp_result.scalars().first()
            if exp:
                ev_result = await db.execute(
                    select(Evidence).where(Evidence.expense_id == exp.id)
                )
                evidence = ev_result.scalars().first()

        if not evidence:
            raise ValueError(f"No evidence found for OCR processing (job_id={job_id}, evidence_id={evidence_id})")

        # Ensure source_event_id is linked to the job
        if not job.source_event_id:
            exp = await db.get(Expense, evidence.expense_id)
            if exp and exp.source_event_id:
                job.source_event_id = exp.source_event_id

        # Create attempt record
        attempt_num = (getattr(task_self.request, "retries", 0) or 0) + 1 if hasattr(task_self, "request") else 1
        attempt = JobAttempt(
            processing_job_id=job.id,
            attempt_number=attempt_num,
        )
        db.add(attempt)
        await db.flush()

        try:
            job.status = JobStatus.RUNNING
            await db.commit()

            storage = create_storage_service()
            file_data = storage.download_file(evidence.object_name)

            ocr_service = create_ocr_service()
            result_data = ocr_service.process_file(file_data)

            attempt.finished_at = datetime.now(UTC)
            attempt.error_message = None

            job.status = JobStatus.SUCCEEDED
            job.result = result_data

            await db.commit()

            logger.info("OCR completed", job_id=str(job.id), confidence=result_data["avg_confidence"])

            return {
                "status": "success",
                "job_id": str(job.id),
                "result": result_data,
            }

        except Exception as e:
            logger.error("OCR failed", job_id=str(job.id), error=str(e))

            attempt.finished_at = datetime.now(UTC)
            attempt.error_message = str(e)
            attempt.error_type = type(e).__name__

            job.status = JobStatus.FAILED

            await db.commit()

            if task_self.request.retries < task_self.max_retries:
                raise task_self.retry(exc=e) from e

            return {
                "status": "failed",
                "job_id": str(job.id),
                "error": str(e),
            }


@celery_app.task
def cleanup_old_jobs(days: int = 30) -> dict:
    """Clean up old processing jobs."""
    return asyncio.run(_cleanup_old_jobs_async(days))


async def _cleanup_old_jobs_async(days: int) -> dict:
    """Async cleanup logic."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        old_jobs_result = await db.execute(
            select(ProcessingJob.id).where(
                ProcessingJob.created_at < cutoff,
                ProcessingJob.status.in_(["SUCCEEDED", "FAILED"]),
            )
        )
        old_job_ids = [row[0] for row in old_jobs_result]

        if old_job_ids:
            await db.execute(
                delete(JobAttempt).where(JobAttempt.processing_job_id.in_(old_job_ids))
            )
            await db.execute(
                delete(ProcessingJob).where(ProcessingJob.id.in_(old_job_ids))
            )
            await db.commit()

        return {
            "status": "success",
            "deleted_jobs": len(old_job_ids),
        }
