"""Posting API endpoints for ledger integration."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_db_dep
from app.core.dependencies import get_current_user as get_current_user_dep
from app.models.user import User
from app.schemas.posting import (
    AccountBalanceListResponse,
    AccountBalanceResponse,
    LedgerEntryResponse,
    PostingDetailResponse,
    PostingListResponse,
    PostingRequest,
    PostingResponse,
    TrialBalanceResponse,
)
from app.services.posting import create_posting_service

router = APIRouter(prefix="/posting", tags=["posting"])


@router.post("/post", response_model=PostingResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_expense(
    request: PostingRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> PostingResponse:
    """Post a reconciled expense to the ledger."""
    posting_service = create_posting_service(db)

    try:
        result = await posting_service.post_expense(
            expense_id=request.expense_id,
            actor_id=current_user.id,
            description=request.description,
            custom_entries=[e.model_dump() for e in request.custom_entries] if request.custom_entries else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return PostingResponse(
        expense_id=result["expense_id"],
        status=result["status"],
        ledger_entries=[
            LedgerEntryResponse(
                id=e["id"],
                ledger_account_id=e["ledger_account_id"],
                ledger_account_name=None,
                ledger_account_type=None,
                expense_id=result["expense_id"],
                amount=Decimal(str(e["amount"])),
                entry_type=e["entry_type"],
                posted_at=e["posted_at"],
                source_audit_event_id=e.get("source_audit_event_id"),
                description=None,
            )
            for e in result["ledger_entries"]
        ],
        message=result.get("message", "Expense posted successfully"),
    )


@router.get("/expense/{expense_id}", response_model=PostingDetailResponse)
async def get_posting(
    expense_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> PostingDetailResponse:
    """Get posting details for an expense."""
    posting_service = create_posting_service(db)
    posting = await posting_service.get_expense_posting(expense_id)

    if not posting:
        raise HTTPException(status_code=404, detail="Posting not found for this expense")

    return PostingDetailResponse(**posting)


@router.get("/", response_model=PostingListResponse)
async def list_postings(
    page: int = 1,
    page_size: int = 20,
    project_id: UUID | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> PostingListResponse:
    """List all postings with pagination."""
    posting_service = create_posting_service(db)
    result = await posting_service.list_postings(
        page=page,
        page_size=page_size,
        project_id=project_id,
    )

    return PostingListResponse(
        items=[PostingDetailResponse(**item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/accounts/balances", response_model=AccountBalanceListResponse)
async def get_account_balances(
    page: int = 1,
    page_size: int = 50,
    project_id: UUID | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> AccountBalanceListResponse:
    """Get current account balances."""
    posting_service = create_posting_service(db)
    result = await posting_service.get_account_balances(
        page=page,
        page_size=page_size,
        project_id=project_id,
    )

    return AccountBalanceListResponse(
        items=[AccountBalanceResponse(**item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def get_trial_balance(
    project_id: UUID | None = None,
    as_of_date: datetime | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> TrialBalanceResponse:
    """Generate trial balance for a project."""
    from datetime import datetime

    posting_service = create_posting_service(db)
    if as_of_date is None:
        as_of_date = datetime.now()

    result = await posting_service.get_trial_balance(
        project_id=project_id,
        as_of_date=as_of_date,
    )

    return TrialBalanceResponse(
        project_id=result.get("project_id"),
        as_of_date=as_of_date,
        accounts=[AccountBalanceResponse(**acc) for acc in result["accounts"]],
        total_debits=result["total_debits"],
        total_credits=result["total_credits"],
        is_balanced=result["is_balanced"],
    )
