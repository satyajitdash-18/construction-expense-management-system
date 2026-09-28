from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_project_manager, require_site_user
from app.schemas.expense import (
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseResponse,
    ExpenseTransitionRequest,
    ExpenseUpdate,
)
from app.services.expense import ExpenseService

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    request: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_site_user),
) -> ExpenseResponse:
    service = ExpenseService(db)
    expense = await service.create_manual_expense(
        project_id=request.project_id,
        created_by=current_user.id,
        transaction_date=request.transaction_date.isoformat(),
        subtotal=float(request.subtotal),
        tax_amount=float(request.tax_amount),
        total=float(request.total),
        currency=request.currency,
        vendor_id=request.vendor_id,
        category_id=request.category_id,
        line_items=[item.model_dump() for item in request.line_items] if request.line_items else None,
        vendor_name=request.vendor_name,
        gstin_supplier=request.gstin_supplier,
        hsn_sac_code=request.hsn_sac_code,
        cgst_amount=float(request.cgst_amount) if request.cgst_amount else None,
        sgst_amount=float(request.sgst_amount) if request.sgst_amount else None,
        igst_amount=float(request.igst_amount) if request.igst_amount else None,
        irn=request.irn,
        payment_method=request.payment_method,
    )
    res = ExpenseResponse.model_validate(expense)
    if not res.vendor_name and request.vendor_name:
        res.vendor_name = request.vendor_name
    return res



@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    project_id: UUID | None = Query(None),
    vendor_id: UUID | None = Query(None),
    category_id: UUID | None = Query(None),
    status: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> "ExpenseListResponse":
    from app.schemas.expense import ExpenseListResponse, ExpenseResponse
    from app.services.expense import ExpenseService

    service = ExpenseService(db)
    expenses = await service.list_expenses(
        project_id=project_id,
        vendor_id=vendor_id,
        category_id=category_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    total = await service.count(
        project_id=project_id,
        vendor_id=vendor_id,
        category_id=category_id,
        status=status,
    )

    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(e) for e in expenses],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> "ExpenseResponse":
    from app.services.expense import ExpenseService

    service = ExpenseService(db)
    expense = await service.get_expense(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: UUID,
    request: "ExpenseUpdate",
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> "ExpenseResponse":
    from app.services.expense import ExpenseService

    service = ExpenseService(db)
    expense = await service.get_expense(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    update_dict = request.model_dump(exclude_unset=True)
    updated_expense = await service.update_expense(
        expense_id=expense_id,
        update_data=update_dict,
        actor_id=current_user.id,
    )
    return ExpenseResponse.model_validate(updated_expense)


@router.post("/{expense_id}/transition", response_model=ExpenseResponse)
async def transition_expense(
    expense_id: UUID,
    request: "ExpenseTransitionRequest",
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_site_user),
) -> "ExpenseResponse":
    from app.services.expense import ExpenseService

    service = ExpenseService(db)
    try:
        expense = await service.transition_status(
            expense_id, request.new_status, actor_id=current_user.id
        )
        return ExpenseResponse.model_validate(expense)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
