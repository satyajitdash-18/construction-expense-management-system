from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.expense_category import ExpenseCategory
from app.schemas.category import (
    ExpenseCategoryCreate,
    ExpenseCategoryResponse,
    ExpenseCategoryUpdate,
)

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[ExpenseCategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> list[ExpenseCategoryResponse]:
    result = await db.execute(select(ExpenseCategory).order_by(ExpenseCategory.name.asc()))
    categories = result.scalars().all()
    return [ExpenseCategoryResponse.model_validate(c) for c in categories]


@router.post("", response_model=ExpenseCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    request: ExpenseCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> ExpenseCategoryResponse:
    existing = await db.execute(
        select(ExpenseCategory).where(ExpenseCategory.name == request.name)
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category with name '{request.name}' already exists",
        )

    category = ExpenseCategory(
        name=request.name,
        parent_category_id=request.parent_category_id,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return ExpenseCategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=ExpenseCategoryResponse)
async def update_category(
    category_id: UUID,
    request: ExpenseCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> ExpenseCategoryResponse:
    category = await db.get(ExpenseCategory, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    if request.name is not None and request.name != category.name:
        existing = await db.execute(
            select(ExpenseCategory).where(ExpenseCategory.name == request.name)
        )
        if existing.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with name '{request.name}' already exists",
            )
        category.name = request.name

    if request.parent_category_id is not None:
        category.parent_category_id = request.parent_category_id

    await db.commit()
    await db.refresh(category)
    return ExpenseCategoryResponse.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> None:
    category = await db.get(ExpenseCategory, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    await db.delete(category)
    await db.commit()
