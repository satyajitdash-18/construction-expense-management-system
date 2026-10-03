"""Extraction API endpoints for LLM-based expense extraction."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import verify_project_access
from app.core.database import get_db as get_db_dep
from app.core.dependencies import get_current_user as get_current_user_dep
from app.core.logging import get_logger
from app.models.enums import JobStatus, JobType
from app.models.evidence import Evidence
from app.models.expense import Expense
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.schemas.extraction import (
    ExtractionJobListResponse,
    ExtractionJobStatus,
    ExtractionProcessResponse,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionValidationResult,
)
from app.services.llm_extraction import ExtractionResult, create_llm_extraction_service
from app.services.validation import create_validation_service
from app.tasks.llm_extraction import process_llm_extraction_task

logger = get_logger(__name__)

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/process", response_model=ExtractionProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_extraction(
    request: ExtractionRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ExtractionProcessResponse:
    """Start LLM extraction on evidence (requires completed OCR)."""
    evidence = await db.get(Evidence, request.evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    expense = await db.get(Expense, evidence.expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Evidence not found")

    await verify_project_access(db, current_user, expense.project_id)
    source_event_id = expense.source_event_id

    if request.use_cached_ocr:
        ocr_job = None
        if source_event_id:
            result = await db.execute(
                select(ProcessingJob).where(
                    ProcessingJob.source_event_id == source_event_id,
                    ProcessingJob.job_type == JobType.OCR,
                    ProcessingJob.status == JobStatus.SUCCEEDED,
                ).order_by(ProcessingJob.created_at.desc())
            )
            ocr_job = result.scalars().first()

        if not ocr_job or not ocr_job.result:
            raise HTTPException(status_code=400, detail="No completed OCR result found. Run OCR first.")

    job = ProcessingJob(
        job_type=JobType.LLM_EXTRACT,
        source_event_id=source_event_id,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    process_llm_extraction_task.delay(str(job.id), str(request.evidence_id))

    return ExtractionProcessResponse(
        job_id=job.id,
        status="PENDING",
        message="LLM extraction started",
    )


@router.post("/process-sync", response_model=ExtractionResponse)
async def extract_sync(
    request: ExtractionRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ExtractionResponse:
    """Run LLM extraction synchronously (for testing/small texts)."""
    evidence = await db.get(Evidence, request.evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    expense = await db.get(Expense, evidence.expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Evidence not found")

    await verify_project_access(db, current_user, expense.project_id)

    if request.use_cached_ocr:
        result = await db.execute(
            select(ProcessingJob).where(
                ProcessingJob.source_event_id == evidence.expense_id,
                ProcessingJob.job_type == JobType.OCR,
                ProcessingJob.status == JobStatus.SUCCEEDED,
            ).order_by(ProcessingJob.created_at.desc())
        )
        ocr_job = result.scalars().first()

        if not ocr_job or not ocr_job.result:
            raise HTTPException(status_code=400, detail="No completed OCR result found. Run OCR first.")

        ocr_text = ocr_job.result.get("full_text", "")
        if not ocr_text:
            raise HTTPException(status_code=400, detail="OCR result contains no text")
    else:
        raise HTTPException(status_code=400, detail="Sync extraction requires cached OCR")

    extraction_service = create_llm_extraction_service()
    extraction_result: ExtractionResult = await extraction_service.extract_expense(ocr_text)

    validation_service = create_validation_service()
    validation = validation_service.validate(extraction_result)
    adjusted_confidence = validation_service.adjust_confidence(extraction_result, validation)

    extraction_result.confidence_score = adjusted_confidence

    if not validation.is_valid:
        logger.warning("Extraction validation failed", errors=validation.errors)

    return ExtractionResponse.model_validate(extraction_result)


@router.get("/jobs/{job_id}", response_model=ExtractionJobStatus)
async def get_extraction_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ExtractionJobStatus:
    """Get extraction job status and results."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Extraction job not found")

    if job.job_type != JobType.LLM_EXTRACT:
        raise HTTPException(status_code=400, detail="Not an LLM extraction job")

    return ExtractionJobStatus.model_validate(job)


@router.get("/jobs", response_model=ExtractionJobListResponse)
async def list_extraction_jobs(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ExtractionJobListResponse:
    """List LLM extraction jobs."""
    offset = (page - 1) * page_size

    query = select(ProcessingJob).where(ProcessingJob.job_type == JobType.LLM_EXTRACT)
    if status_filter:
        query = query.where(ProcessingJob.status == JobStatus(status_filter))

    query = query.offset(offset).limit(page_size).order_by(ProcessingJob.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    count_query = select(ProcessingJob).where(ProcessingJob.job_type == JobType.LLM_EXTRACT)
    if status_filter:
        count_query = count_query.where(ProcessingJob.status == JobStatus(status_filter))
    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    return ExtractionJobListResponse(
        items=[ExtractionJobStatus.model_validate(j) for j in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/jobs/{job_id}/retry", response_model=ExtractionJobStatus)
async def retry_extraction_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ExtractionJobStatus:
    """Retry a failed extraction job."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Extraction job not found")

    if job.job_type != JobType.LLM_EXTRACT:
        raise HTTPException(status_code=400, detail="Not an LLM extraction job")

    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    job.status = JobStatus.PENDING
    job.result = None
    await db.commit()
    await db.refresh(job)

    # Find evidence for this job via expense
    evidence = None
    if job.source_event_id:
        exp_res = await db.execute(
            select(Expense).where(Expense.source_event_id == job.source_event_id)
        )
        exp = exp_res.scalars().first()
        if exp:
            ev_res = await db.execute(
                select(Evidence).where(Evidence.expense_id == exp.id)
            )
            evidence = ev_res.scalars().first()

    if evidence:
        process_llm_extraction_task.delay(str(job.id), str(evidence.id))
    else:
        process_llm_extraction_task.delay(str(job.id))

    return ExtractionJobStatus.model_validate(job)


@router.post("/validate", response_model=ExtractionValidationResult)
async def validate_extraction(
    extraction: ExtractionResponse,
    current_user: User = Depends(get_current_user_dep),
) -> ExtractionValidationResult:
    """Validate extraction result and get confidence adjustment."""
    validation_service = create_validation_service()
    return validation_service.validate(extraction)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extraction_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> None:
    """Delete an extraction job."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Extraction job not found")

    if job.job_type != JobType.LLM_EXTRACT:
        raise HTTPException(status_code=400, detail="Not an LLM extraction job")

    await db.delete(job)
    await db.commit()
