"""LLM extraction Celery tasks."""

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
from app.services.llm_extraction import ExtractionResult, create_llm_extraction_service

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def process_llm_extraction_task(task_self: Celery, job_id: str, evidence_id: str | None = None) -> dict:
    """
    Process LLM extraction on OCR result.

    Args:
        job_id: ProcessingJob ID
        evidence_id: Optional Evidence ID (for direct evidence processing)

    Returns:
        Extraction result dict
    """
    return asyncio.run(_process_llm_extraction_async(task_self, job_id, evidence_id))


async def _process_llm_extraction_async(
    task_self: Celery,
    job_id: str,
    evidence_id: str | None = None,
) -> dict:
    """Async LLM extraction processing logic."""
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

        # Link source_event_id on job if missing
        if not job.source_event_id and evidence:
            exp = await db.get(Expense, evidence.expense_id)
            if exp and exp.source_event_id:
                job.source_event_id = exp.source_event_id

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

            # Look up completed OCR job for this source event / expense
            ocr_job = None
            if job.source_event_id:
                ocr_job_result = await db.execute(
                    select(ProcessingJob).where(
                        ProcessingJob.source_event_id == job.source_event_id,
                        ProcessingJob.job_type == JobType.OCR,
                        ProcessingJob.status == JobStatus.SUCCEEDED,
                    ).order_by(ProcessingJob.created_at.desc())
                )
                ocr_job = ocr_job_result.scalars().first()

            if not ocr_job and evidence:
                exp = await db.get(Expense, evidence.expense_id)
                if exp and exp.source_event_id:
                    ocr_job_result = await db.execute(
                        select(ProcessingJob).where(
                            ProcessingJob.source_event_id == exp.source_event_id,
                            ProcessingJob.job_type == JobType.OCR,
                            ProcessingJob.status == JobStatus.SUCCEEDED,
                        ).order_by(ProcessingJob.created_at.desc())
                    )
                    ocr_job = ocr_job_result.scalars().first()

            if not ocr_job or not ocr_job.result:
                raise ValueError("No completed OCR result found for this expense")

            ocr_result: dict = ocr_job.result  # type: ignore[assignment]
            ocr_text = ocr_result.get("full_text") or ocr_result.get("text", "")
            if not ocr_text:
                raise ValueError("OCR result contains no text")

            extraction_service = create_llm_extraction_service()
            extraction_result: ExtractionResult = await extraction_service.extract_expense(ocr_text)

            attempt.finished_at = datetime.now(UTC)
            attempt.error_message = None

            job.status = JobStatus.SUCCEEDED
            job.result = extraction_result.model_dump()

            await db.commit()

            logger.info(
                "LLM extraction completed",
                job_id=str(job.id),
                confidence=extraction_result.confidence_score,
            )

            return {
                "status": "success",
                "job_id": str(job.id),
                "result": extraction_result.model_dump(),
            }

        except Exception as e:
            logger.error("LLM extraction failed", job_id=str(job.id), error=str(e))

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
def cleanup_failed_extractions(days: int = 7) -> dict:
    """Clean up failed extraction jobs."""
    return asyncio.run(_cleanup_failed_extractions_async(days))


async def _cleanup_failed_extractions_async(days: int) -> dict:
    """Async cleanup logic."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProcessingJob.id).where(
                ProcessingJob.created_at < cutoff,
                ProcessingJob.job_type == JobType.LLM_EXTRACT,
                ProcessingJob.status == JobStatus.FAILED,
            )
        )
        failed_job_ids = [row[0] for row in result]

        if failed_job_ids:
            await db.execute(
                delete(JobAttempt).where(JobAttempt.processing_job_id.in_(failed_job_ids))
            )
            await db.execute(
                delete(ProcessingJob).where(ProcessingJob.id.in_(failed_job_ids))
            )
            await db.commit()

        return {
            "status": "success",
            "deleted_jobs": len(failed_job_ids),
        }
