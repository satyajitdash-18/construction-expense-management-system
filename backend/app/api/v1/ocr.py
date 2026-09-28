"""OCR API endpoints for text extraction."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import JobStatus, JobType
from app.models.evidence import Evidence
from app.models.expense import Expense
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.schemas.ocr import (
    OCRJobListResponse,
    OCRJobStatus,
    OCRProcessRequest,
    OCRProcessResponse,
)
from app.tasks.ocr import process_ocr_task

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post("/process", response_model=OCRProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_ocr_processing(
    request: OCRProcessRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OCRProcessResponse:
    """Start OCR processing on an evidence file."""
    evidence = await db.get(Evidence, request.evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    expense = await db.get(Expense, evidence.expense_id)
    source_event_id = expense.source_event_id if expense else None

    # Create processing job
    job = ProcessingJob(
        job_type=JobType.OCR,
        source_event_id=source_event_id,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Queue OCR task after transaction commit
    process_ocr_task.delay(str(job.id), str(request.evidence_id))

    return OCRProcessResponse(
        job_id=job.id,
        status="PENDING",
        message="OCR processing started",
    )


@router.get("/jobs/{job_id}", response_model=OCRJobStatus)
async def get_ocr_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OCRJobStatus:
    """Get OCR job status and results."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="OCR job not found")

    return OCRJobStatus.model_validate(job)


@router.get("/jobs", response_model=OCRJobListResponse)
async def list_ocr_jobs(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OCRJobListResponse:
    """List OCR processing jobs."""
    offset = (page - 1) * page_size

    query = select(ProcessingJob).where(ProcessingJob.job_type == JobType.OCR)
    if status_filter:
        query = query.where(ProcessingJob.status == JobStatus(status_filter))

    query = query.offset(offset).limit(page_size).order_by(ProcessingJob.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    # Count total
    count_query = select(ProcessingJob).where(ProcessingJob.job_type == JobType.OCR)
    if status_filter:
        count_query = count_query.where(ProcessingJob.status == JobStatus(status_filter))
    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    return OCRJobListResponse(
        items=[OCRJobStatus.model_validate(j) for j in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/jobs/{job_id}/retry", response_model=OCRJobStatus)
async def retry_ocr_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OCRJobStatus:
    """Retry a failed OCR job."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="OCR job not found")

    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    # Reset job status
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
        process_ocr_task.delay(str(job.id), str(evidence.id))
    else:
        process_ocr_task.delay(str(job.id))

    return OCRJobStatus.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ocr_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an OCR job and its attempts."""
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="OCR job not found")

    await db.delete(job)
    await db.commit()
