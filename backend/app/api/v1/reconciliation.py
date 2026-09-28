"""Reconciliation API endpoints for expense-payment matching."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_db_dep
from app.core.dependencies import get_current_user as get_current_user_dep
from app.models.enums import MatchBasis
from app.models.expense import Expense
from app.models.payment_event import PaymentEvent
from app.models.user import User
from app.schemas.reconciliation import (
    AutoMatchRequest,
    AutoMatchResult,
    ReconciliationActionRequest,
    ReconciliationDetailResponse,
    ReconciliationListResponse,
    ReconciliationRecordResponse,
    ReconciliationRequest,
    ReconciliationStats,
)
from app.services.reconciliation import create_reconciliation_service

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.post("", response_model=ReconciliationRecordResponse | dict, status_code=status.HTTP_201_CREATED)
@router.post("/match", response_model=ReconciliationRecordResponse | dict, status_code=status.HTTP_202_ACCEPTED)
async def reconcile_expense(

    request: ReconciliationRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ReconciliationRecordResponse | dict:
    """Find matching payment events for an expense (or create reconciliation if payment_event_id provided)."""
    reconciliation_service = create_reconciliation_service(db)

    expense = await db.get(Expense, request.expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if request.payment_event_id:
        # Manual match
        payment = await db.get(PaymentEvent, request.payment_event_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment event not found")

        record = await reconciliation_service.create_reconciliation(
            expense_id=request.expense_id,
            payment_event_id=request.payment_event_id,
            match_basis=MatchBasis.MANUAL,
            match_score=Decimal("1.0"),
            resolved_by=current_user.id,
        )
        return ReconciliationRecordResponse.model_validate(record)
    else:
        # Auto-match
        candidates = await reconciliation_service.find_candidates(expense)
        return {"candidates": candidates}


@router.post("/auto-match", response_model=AutoMatchResult, status_code=status.HTTP_202_ACCEPTED)
async def auto_match(
    request: AutoMatchRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> AutoMatchResult:
    """Run auto-matching for expenses."""
    reconciliation_service = create_reconciliation_service(db)

    result = await reconciliation_service.auto_match_batch(
        project_id=request.project_id,
        date_from=request.date_from,
        date_to=request.date_to,
        confidence_threshold=Decimal(str(request.confidence_threshold)),
        dry_run=request.dry_run,
    )

    return AutoMatchResult(**result)


@router.get("/records", response_model=ReconciliationListResponse)
async def list_reconciliations(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    project_id: UUID | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ReconciliationListResponse:
    """List reconciliation records."""
    reconciliation_service = create_reconciliation_service(db)
    result = await reconciliation_service.list_reconciliations(
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        project_id=project_id,
    )

    items = [
        ReconciliationDetailResponse(
            id=item["id"],
            expense_id=item["expense_id"],
            expense_vendor=item.get("expense_vendor"),
            expense_amount=item["expense_amount"],
            expense_date=item.get("expense_date"),
            payment_event_id=item.get("payment_event_id"),
            payment_amount=item.get("payment_amount"),
            payment_date=item.get("payment_date"),
            payment_payee=item.get("payment_payee"),
            payment_upi_ref=item.get("payment_upi_ref"),
            payment_bank_ref=item.get("payment_bank_ref"),
            status=item["status"],
            match_basis=item.get("match_basis"),
            match_score=item.get("match_score"),
            resolved_by=item.get("resolved_by"),
            resolution_reason=item.get("resolution_reason"),
            created_at=item["created_at"],
            updated_at=item.get("updated_at"),
        )
        for item in result["items"]
    ]

    return ReconciliationListResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/records/{record_id}", response_model=ReconciliationDetailResponse)
async def get_reconciliation(
    record_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ReconciliationDetailResponse:
    """Get detailed reconciliation record."""
    from app.models.expense import Expense
    from app.models.payment_event import PaymentEvent
    from app.models.reconciliation_record import ReconciliationRecord

    record = await db.get(ReconciliationRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Reconciliation record not found")

    expense = await db.get(Expense, record.expense_id)
    payment = await db.get(PaymentEvent, record.payment_event_id) if record.payment_event_id else None

    return ReconciliationDetailResponse(
        id=record.id,
        expense_id=record.expense_id,
        expense_vendor=expense.vendor.name if expense and expense.vendor else None,
        expense_amount=float(expense.total) if expense else 0,
        expense_date=expense.transaction_date.isoformat() if expense and expense.transaction_date else None,
        payment_event_id=record.payment_event_id,
        payment_amount=float(payment.amount) if payment else None,
        payment_date=payment.occurred_at.isoformat() if payment else None,
        payment_payee=payment.payee_raw_text if payment else None,
        payment_upi_ref=payment.upi_reference if payment else None,
        payment_bank_ref=payment.bank_reference if payment else None,
        status=record.status.value,
        match_basis=record.match_basis.value if record.match_basis else None,
        match_score=float(record.match_score) if record.match_score else None,
        resolved_by=record.resolved_by,
        resolution_reason=record.resolution_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("/records/{record_id}/action", response_model=ReconciliationRecordResponse)
async def take_reconciliation_action(
    record_id: UUID,
    request: ReconciliationActionRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ReconciliationRecordResponse:
    """Confirm, reject, or unmatch a reconciliation."""
    reconciliation_service = create_reconciliation_service(db)
    reviewer_id = current_user.id

    if request.action == "confirm":
        record = await reconciliation_service.confirm_reconciliation(
            reconciliation_id=record_id,
            reviewer_id=reviewer_id,
            notes=request.notes,
            match_basis=MatchBasis(request.match_basis) if request.match_basis else None,
        )
    elif request.action == "reject":
        record = await reconciliation_service.reject_reconciliation(
            reconciliation_id=record_id,
            reviewer_id=reviewer_id,
            notes=request.notes,
        )
    elif request.action == "unmatch":
        record = await reconciliation_service.unmatch_reconciliation(
            reconciliation_id=record_id,
            reviewer_id=reviewer_id,
            notes=request.notes,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

    return ReconciliationRecordResponse.model_validate(record)


@router.get("/stats", response_model=ReconciliationStats)
async def get_reconciliation_stats(
    project_id: UUID | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ReconciliationStats:
    """Get reconciliation statistics."""
    reconciliation_service = create_reconciliation_service(db)
    stats = await reconciliation_service.get_reconciliation_stats(project_id=project_id)
    return ReconciliationStats(**stats)


@router.post("/auto-match-batch", response_model=AutoMatchResult, status_code=status.HTTP_202_ACCEPTED)
async def auto_match_batch(
    request: AutoMatchRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> AutoMatchResult:
    """Run batch auto-matching for multiple expenses."""
    reconciliation_service = create_reconciliation_service(db)

    result = await reconciliation_service.auto_match_batch(
        project_id=request.project_id,
        date_from=request.date_from,
        date_to=request.date_to,
        confidence_threshold=Decimal(str(request.confidence_threshold)),
        dry_run=request.dry_run,
    )

    return AutoMatchResult(**result)
