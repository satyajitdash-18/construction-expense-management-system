from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import (
    get_user_accessible_project_ids,
    verify_project_access,
)
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_project_manager
from app.schemas.project import (
    BudgetCreate,
    BudgetVsActualResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.project import ProjectService

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> ProjectResponse:
    service = ProjectService(db)
    try:
        project = await service.create_project(
            name=request.name,
            code=request.code,
            created_by=current_user.id,
            status=request.status,
        )
        await db.commit()
        return ProjectResponse.model_validate(project)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> ProjectListResponse:
    service = ProjectService(db)
    accessible_ids = await get_user_accessible_project_ids(db, current_user)
    projects = await service.list_projects(
        status_filter=status,
        project_ids=accessible_ids,
        limit=limit,
        offset=offset,
    )
    total = await service.get_project_count(
        status_filter=status,
        project_ids=accessible_ids,
    )

    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> ProjectResponse:
    await verify_project_access(db, current_user, project_id)
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    request: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> ProjectResponse:
    await verify_project_access(db, current_user, project_id, ["admin", "project_manager"])
    service = ProjectService(db)
    project = await service.update_project(
        project_id=project_id,
        name=request.name,
        status=request.status,
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await db.commit()
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> None:
    await verify_project_access(db, current_user, project_id, ["admin", "project_manager"])
    service = ProjectService(db)
    deleted = await service.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await db.commit()


@router.get("/{project_id}/budget", response_model=dict)
@router.get("/{project_id}/budget-vs-actual", response_model=dict)
async def get_budget_vs_actual(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> dict:
    await verify_project_access(db, current_user, project_id)
    service = ProjectService(db)
    data = await service.get_budget_vs_actual(project_id)
    return {
        **data,
        "budget": data.get("total_budget", 0),
        "actual": data.get("total_actual", 0),
        "variance": data.get("remaining", 0),
    }


@router.post("/{project_id}/budget", status_code=status.HTTP_201_CREATED)
@router.post("/{project_id}/budgets", status_code=status.HTTP_201_CREATED)
async def set_budget(
    project_id: UUID,
    request: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> dict:
    await verify_project_access(db, current_user, project_id, ["admin", "project_manager"])
    service = ProjectService(db)
    budget = await service.set_budget(
        project_id=project_id,
        amount=request.amount,
        currency=request.currency,
        category_id=request.category_id,
        effective_from=request.effective_from,
        effective_to=request.effective_to,
    )
    await db.commit()
    return {
        "id": str(budget.id),
        "project_id": str(project_id),
        "amount": float(budget.amount),
        "currency": budget.currency,
        "message": "Budget created",
    }


@router.get("/{project_id}/budgets")
async def get_budgets(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> list[dict]:
    await verify_project_access(db, current_user, project_id)
    service = ProjectService(db)
    budgets = await service.get_budgets(project_id)
    return [
        {
            "id": str(b.id),
            "amount": float(b.amount),
            "currency": b.currency,
            "category_id": str(b.category_id) if b.category_id else None,
            "effective_from": b.effective_from.isoformat() if b.effective_from else None,
            "effective_to": b.effective_to.isoformat() if b.effective_to else None,
        }
        for b in budgets
    ]


@router.get("/{project_id}/members", response_model=list[dict])
async def list_project_members(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> list[dict]:
    await verify_project_access(db, current_user, project_id)
    service = ProjectService(db)
    members = await service.list_members(project_id)
    return [
        {
            "id": str(m.id),
            "project_id": str(m.project_id),
            "user_id": str(m.user_id),
            "role": m.role,
            "created_at": m.created_at.isoformat(),
        }
        for m in members
    ]


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: UUID,
    request: ProjectMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> dict:
    await verify_project_access(db, current_user, project_id, ["admin", "project_manager"])
    service = ProjectService(db)
    member = await service.add_member(project_id, request.user_id, request.role)
    await db.commit()
    return {
        "id": str(member.id),
        "project_id": str(member.project_id),
        "user_id": str(member.user_id),
        "role": member.role,
        "message": "Member added successfully",
    }


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(require_project_manager),
) -> None:
    await verify_project_access(db, current_user, project_id, ["admin", "project_manager"])
    service = ProjectService(db)
    removed = await service.remove_member(project_id, user_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found on this project")
    await db.commit()
