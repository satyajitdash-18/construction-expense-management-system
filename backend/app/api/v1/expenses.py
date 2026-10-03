from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import (
    get_user_accessible_project_ids,
    verify_project_access,
)
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
    # Verify user has site_user/PM/admin access on the target project
    await verify_project_access(
        db,
        current_user,
        request.project_id,
        ["admin", "project_manager", "site_user"],
    )

    service = ExpenseService(db)
    expense = await service.create_manual_expense(
        project_id=request.project_id,
        created_by=current_user.id,
        transaction_date=request.transaction_date.isoformat(),
        subtotal=request.subtotal,
        tax_amount=request.tax_amount,
        total=request.total,
        currency=request.currency,
        vendor_id=request.vendor_id,
        category_id=request.category_id,
        line_items=[item.model_dump() for item in request.line_items] if request.line_items else None,
        vendor_name=request.vendor_name,
        gstin_supplier=request.gstin_supplier,
        hsn_sac_code=request.hsn_sac_code,
        cgst_amount=request.cgst_amount,
        sgst_amount=request.sgst_amount,
        igst_amount=request.igst_amount,
        irn=request.irn,
        payment_method=request.payment_method,
    )
    await db.commit()

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
) -> ExpenseListResponse:
    service = ExpenseService(db)

    # Scoping check
    accessible_project_ids = await get_user_accessible_project_ids(db, current_user)
    if project_id:
        if accessible_project_ids is not None and project_id not in accessible_project_ids:
            return ExpenseListResponse(items=[], total=0, limit=limit, offset=offset)
        accessible_project_ids = [project_id]

    expenses = await service.list_expenses(
        project_id=project_id,
        project_ids=accessible_project_ids,
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
        project_ids=accessible_project_ids,
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
) -> ExpenseResponse:
    service = ExpenseService(db)
    expense = await service.get_expense(expense_id)
    if not expense:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    await verify_project_access(db, current_user, expense.project_id)
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: UUID,
    request: ExpenseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> ExpenseResponse:
    service = ExpenseService(db)
    expense = await service.get_expense(expense_id)
    if not expense:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    await verify_project_access(db, current_user, expense.project_id, ["admin", "project_manager"])

    update_dict = request.model_dump(exclude_unset=True)
    try:
        updated_expense = await service.update_expense(
            expense_id=expense_id,
            update_data=update_dict,
            actor_id=current_user.id,
        )
        await db.commit()
        return ExpenseResponse.model_validate(updated_expense)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/{expense_id}/transition", response_model=ExpenseResponse)
async def transition_expense(
    expense_id: UUID,
    request: ExpenseTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_site_user),
) -> ExpenseResponse:
    service = ExpenseService(db)
    expense = await service.get_expense(expense_id)
    if not expense:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")

    await verify_project_access(
        db,
        current_user,
        expense.project_id,
        ["admin", "project_manager", "site_user"],
    )

    try:
        updated_expense = await service.transition_status(
            expense_id, request.new_status, actor_id=current_user.id
        )
        await db.commit()
        return ExpenseResponse.model_validate(updated_expense)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
