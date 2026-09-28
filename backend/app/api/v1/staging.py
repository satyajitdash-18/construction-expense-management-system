"""Staging API endpoints for human review workflow."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_db_dep
from app.core.dependencies import get_current_user as get_current_user_dep
from app.models.user import User
from app.schemas.staging import (
    StageActionRequest,
    StageActionResponse,
    StagedExpenseDetail,
    StagedExpenseItem,
    StagedListResponse,
    StagingRequest,
    StagingResponse,
    StagingStats,
)
from app.services.staging import create_staging_service

router = APIRouter(prefix="/staging", tags=["staging"])


@router.post("/stage", response_model=StagingResponse, status_code=status.HTTP_202_ACCEPTED)
async def stage_expenses(
    request: StagingRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> StagingResponse:
    """Stage expenses for human review."""
    if not request.expense_ids:
        raise HTTPException(status_code=400, detail="No expense IDs provided")

    staging_service = create_staging_service(db)
    result = await staging_service.stage_expenses(
        expense_ids=request.expense_ids,
        reviewer_id=current_user.id,
        notes=request.notes,
    )

    if result["errors"]:
        pass  # Some expenses could not be staged - log in production

    staged_items = [
        StagedExpenseItem(
            expense_id=item["expense_id"],
            vendor_name=item.get("vendor_name"),
            vendor_gstin=item.get("vendor_gstin"),
            transaction_date=item.get("transaction_date"),
            invoice_number=item.get("invoice_number"),
            subtotal=item.get("subtotal"),
            tax_amount=item.get("tax_amount"),
            total_amount=item.get("total_amount"),
            currency=item.get("currency", "INR"),
            payment_method=item.get("payment_method"),
            confidence_score=item.get("confidence_score", 0.0),
            extraction_result=item.get("extraction_result"),
            validation_errors=item.get("validation_errors", []),
            validation_warnings=item.get("validation_warnings", []),
        )
        for item in result["staged_expenses"]
    ]

    return StagingResponse(
        staged_count=result["staged_count"],
        message=f"Staged {result['staged_count']} expenses for review",
        staged_expenses=staged_items,
    )


@router.get("/expenses", response_model=StagedListResponse)
async def list_staged_expenses(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> StagedListResponse:
    """List staged expenses with pagination."""
    staging_service = create_staging_service(db)
    result = await staging_service.list_staged_expenses(
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )

    items = [
        StagedExpenseDetail(
            expense_id=item["expense_id"],
            project_id=item["project_id"],
            project_name=item.get("project_name"),
            source_event_id=item.get("source_event_id"),
            evidence_ids=item["evidence_ids"],
            vendor_name=item.get("vendor_name"),
            vendor_gstin=item.get("vendor_gstin"),
            transaction_date=item.get("transaction_date"),
            invoice_number=item.get("invoice_number"),
            subtotal=item.get("subtotal"),
            tax_amount=item.get("tax_amount"),
            total_amount=item.get("total_amount"),
            currency=item.get("currency", "INR"),
            payment_method=item.get("payment_method"),
            cgst_amount=item.get("cgst_amount"),
            sgst_amount=item.get("sgst_amount"),
            igst_amount=item.get("igst_amount"),
            hsn_sac_code=item.get("hsn_sac_code"),
            irn=item.get("irn"),
            confidence_score=item.get("confidence_score", 0.0),
            extraction_result=item.get("extraction_result"),
            validation_errors=item.get("validation_errors", []),
            validation_warnings=item.get("validation_warnings", []),
            line_items=item.get("line_items", []),
            staged_at=item.get("staged_at"),
            staged_by=item.get("staged_by"),
            reviewer_id=item.get("reviewer_id"),
            reviewed_at=item.get("reviewed_at"),
            review_notes=item.get("review_notes"),
        )
        for item in result["items"]
    ]

    return StagedListResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/expenses/{expense_id}", response_model=StagedExpenseDetail)
async def get_staged_expense(
    expense_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> StagedExpenseDetail:
    """Get detailed staged expense for review."""
    staging_service = create_staging_service(db)
    expense = await staging_service.get_staged_expense(expense_id)

    if not expense:
        raise HTTPException(status_code=404, detail="Staged expense not found")

    return StagedExpenseDetail(**expense)


@router.post("/expenses/{expense_id}/action", response_model=StageActionResponse)
async def take_stage_action(
    expense_id: UUID,
    request: StageActionRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> StageActionResponse:
    """Approve, reject, or request changes for a staged expense."""
    staging_service = create_staging_service(db)
    reviewer_id = current_user.id

    if request.action == "approve":
        result = await staging_service.approve_expense(
            expense_id=expense_id,
            reviewer_id=reviewer_id,
            notes=request.notes,
        )
    elif request.action == "reject":
        result = await staging_service.reject_expense(
            expense_id=expense_id,
            reviewer_id=reviewer_id,
            notes=request.notes,
        )
    elif request.action == "request_changes":
        result = await staging_service.request_changes(
            expense_id=expense_id,
            reviewer_id=reviewer_id,
            notes=request.notes,
            corrections=request.corrections,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

    return StageActionResponse(
        expense_id=result["expense_id"],
        action=result["action"],
        new_status=result["new_status"],
        message=result["message"],
    )


@router.get("/stats", response_model=StagingStats)
async def get_staging_stats(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> StagingStats:
    """Get staging statistics."""
    staging_service = create_staging_service(db)
    stats = await staging_service.get_staging_stats()
    return StagingStats(**stats)
