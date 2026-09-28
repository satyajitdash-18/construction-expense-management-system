"""Standalone /budgets endpoint that accepts project_id in the request body."""

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_project_manager
from app.schemas.project import BudgetCreate
from app.services.project import ProjectService

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/budgets", tags=["budgets"])


class _BudgetCreateBody(BudgetCreate):
    """Budget create with required project_id in body."""
    project_id: UUID  # Override to make required


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_budget(
    request: _BudgetCreateBody,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> dict:
    """Create a budget entry for a project (project_id provided in body)."""
    service = ProjectService(db)
    project = await service.get_project(request.project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    budget = await service.set_budget(
        project_id=request.project_id,
        amount=request.amount,
        currency=request.currency,
        category_id=request.category_id,
        effective_from=request.effective_from,
        effective_to=request.effective_to,
    )
    return {
        "id": str(budget.id),
        "project_id": str(request.project_id),
        "amount": float(budget.amount),
        "currency": budget.currency,
        "category": request.category,
        "message": "Budget created",
    }
