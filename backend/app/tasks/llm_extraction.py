"""LLM extraction Celery tasks."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from celery import Celery
from sqlalchemy import delete, func, select

from app.audit.helper import write_audit_event
from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.enums import JobStatus, JobType, LifecycleStatus, PaymentMethod
from app.models.evidence import Evidence
from app.models.expense import Expense
from app.models.processing_job import JobAttempt, ProcessingJob
from app.models.project import Project
from app.models.source_event import SourceEvent
from app.models.vendor import Vendor
from app.services.llm_extraction import ExtractionResult, create_llm_extraction_service

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def process_llm_extraction_task(task_self: Celery, job_id: str, evidence_id: str | None = None) -> dict:
    """
    Process LLM extraction on text (from OCR result or direct text input).

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
    """Async LLM extraction processing logic supporting both OCR and direct text workflows."""
    job_uuid = UUID(job_id)
    evidence_uuid = UUID(evidence_id) if evidence_id else None

    async with AsyncSessionLocal() as db:
        # Retrieve the specific processing job passed by caller
        job = await db.get(ProcessingJob, job_uuid)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Resolve evidence if provided
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

            # Resolve text to extract:
            # 1. Check for direct text in SourceEvent (e.g. WhatsApp text)
            # 2. Fall back to completed OCR job result
            raw_text = None
            if job.source_event_id:
                source_event = await db.get(SourceEvent, job.source_event_id)
                if source_event and isinstance(source_event.raw_payload, dict):
                    raw_text = source_event.raw_payload.get("text")

            if not raw_text:
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

                if ocr_job and ocr_job.result:
                    ocr_result: dict = ocr_job.result  # type: ignore[assignment]
                    raw_text = ocr_result.get("full_text") or ocr_result.get("text", "")

            if not raw_text or not raw_text.strip():
                raise ValueError("No text provided and no completed OCR result found for this expense")

            extraction_service = create_llm_extraction_service()
            extraction_result: ExtractionResult = await extraction_service.extract_expense(raw_text)

            attempt.finished_at = datetime.now(UTC)
            attempt.error_message = None

            job.status = JobStatus.SUCCEEDED
            job.result = extraction_result.model_dump()

            # Check if an existing Expense is associated with this job
            expense = None
            if job.source_event_id:
                exp_result = await db.execute(
                    select(Expense).where(Expense.source_event_id == job.source_event_id)
                )
                expense = exp_result.scalars().first()

            if not expense and evidence and evidence.expense_id:
                expense = await db.get(Expense, evidence.expense_id)

            if expense:
                # Update existing expense with extracted fields
                if extraction_result.total_amount is not None:
                    expense.total = Decimal(str(extraction_result.total_amount))
                    expense.subtotal = Decimal(str(extraction_result.subtotal or extraction_result.total_amount))
                if extraction_result.tax_amount is not None:
                    expense.tax_amount = Decimal(str(extraction_result.tax_amount))
                if extraction_result.transaction_date:
                    try:
                        expense.transaction_date = date.fromisoformat(extraction_result.transaction_date)
                    except ValueError:
                        pass
                if extraction_result.vendor_gstin:
                    expense.gstin_supplier = extraction_result.vendor_gstin
                if extraction_result.confidence_score is not None:
                    expense.confidence_score = Decimal(str(round(extraction_result.confidence_score, 2)))
                expense.lifecycle_status = (
                    LifecycleStatus.STAGED if (extraction_result.confidence_score or 0) >= 0.7 else LifecycleStatus.NEEDS_CONFIRMATION
                )
                await db.flush()

                await write_audit_event(
                    session=db,
                    event_type="expense.extracted",
                    entity_type="expense",
                    entity_id=expense.id,
                    actor_id=None,
                    payload={
                        "job_id": str(job.id),
                        "confidence_score": extraction_result.confidence_score,
                        "vendor_name": extraction_result.vendor_name,
                        "total_amount": extraction_result.total_amount,
                    },
                )
            elif job.source_event_id:
                # Direct text from WhatsApp without an existing Expense: create new Expense
                target_project = None
                if source_event and source_event.raw_payload.get("project_id"):
                    try:
                        target_project = await db.get(Project, UUID(str(source_event.raw_payload["project_id"])))
                    except Exception:
                        pass
                if not target_project:
                    proj_result = await db.execute(
                        select(Project).order_by(Project.created_at.desc()).limit(1)
                    )
                    target_project = proj_result.scalars().first()

                if target_project:
                    tot = Decimal(str(extraction_result.total_amount or 0))
                    sub = Decimal(str(extraction_result.subtotal or tot))
                    tax = Decimal(str(extraction_result.tax_amount or 0))
                    tx_date = date.today()
                    if extraction_result.transaction_date:
                        try:
                            tx_date = date.fromisoformat(extraction_result.transaction_date)
                        except ValueError:
                            pass

                    vendor_id = None
                    if extraction_result.vendor_name:
                        v_res = await db.execute(
                            select(Vendor).where(func.lower(Vendor.name) == extraction_result.vendor_name.lower().strip())
                        )
                        vendor = v_res.scalars().first()
                        if not vendor:
                            vendor = Vendor(
                                name=extraction_result.vendor_name.strip(),
                                gstin=extraction_result.vendor_gstin,
                            )
                            db.add(vendor)
                            await db.flush()
                        vendor_id = vendor.id

                    expense = Expense(
                        project_id=target_project.id,
                        source_event_id=job.source_event_id,
                        vendor_id=vendor_id,
                        transaction_date=tx_date,
                        subtotal=sub,
                        tax_amount=tax,
                        total=tot,
                        currency=extraction_result.currency or "INR",
                        payment_method=(
                            PaymentMethod(extraction_result.payment_method)
                            if extraction_result.payment_method in [p.value for p in PaymentMethod]
                            else PaymentMethod.CASH
                        ),
                        gstin_supplier=extraction_result.vendor_gstin,
                        hsn_sac_code=extraction_result.hsn_sac_code,
                        cgst_amount=Decimal(str(extraction_result.cgst_amount)) if extraction_result.cgst_amount is not None else None,
                        sgst_amount=Decimal(str(extraction_result.sgst_amount)) if extraction_result.sgst_amount is not None else None,
                        igst_amount=Decimal(str(extraction_result.igst_amount)) if extraction_result.igst_amount is not None else None,
                        irn=extraction_result.irn,
                        confidence_score=Decimal(str(round(extraction_result.confidence_score, 2))) if extraction_result.confidence_score is not None else Decimal("0.85"),
                        lifecycle_status=(
                            LifecycleStatus.STAGED if (extraction_result.confidence_score or 0) >= 0.7 else LifecycleStatus.NEEDS_CONFIRMATION
                        ),
                    )
                    db.add(expense)
                    await db.flush()

                    await write_audit_event(
                        session=db,
                        event_type="expense.created_from_text",
                        entity_type="expense",
                        entity_id=expense.id,
                        actor_id=None,
                        payload={
                            "source": "whatsapp_text",
                            "source_event_id": str(job.source_event_id),
                            "total": float(tot),
                            "vendor_name": extraction_result.vendor_name,
                        },
                    )

            await db.commit()

            logger.info(
                "LLM extraction completed",
                job_id=str(job.id),
                confidence=extraction_result.confidence_score,
                expense_id=str(expense.id) if expense else None,
            )

            return {
                "status": "success",
                "job_id": str(job.id),
                "result": extraction_result.model_dump(),
                "expense_id": str(expense.id) if expense else None,
            }

        except Exception as e:
            logger.error("LLM extraction failed", job_id=str(job.id), error=str(e))

            attempt.finished_at = datetime.now(UTC)
            attempt.error_message = str(e)
            attempt.error_type = type(e).__name__

            job.status = JobStatus.FAILED

            await db.commit()

            if hasattr(task_self, "request") and task_self.request and task_self.request.retries < task_self.max_retries:
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
