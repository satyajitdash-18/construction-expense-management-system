"""Scoped /audit/logs endpoint with strict tenant and RBAC isolation."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import get_user_accessible_project_ids
from app.core.database import get_db as get_db_dep
from app.core.dependencies import get_current_user as get_current_user_dep
from app.models.audit_event import AuditEvent
from app.models.expense import Expense
from app.models.project_budget import ProjectBudget
from app.models.user import User
from app.schemas.audit_compliance import AuditEventResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=dict)
async def list_audit_logs(
    project_id: UUID | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict[str, Any]:
    """List audit log events with tenant project scoping and database-level filtering."""
    accessible_project_ids = await get_user_accessible_project_ids(db, current_user)

    conditions = []
    if entity_type:
        conditions.append(AuditEvent.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditEvent.entity_id == entity_id)

    # Tenant scoping enforcement in SQL
    if accessible_project_ids is not None:
        # Non-admin user: restrict to accessible projects or self-initiated actions
        if project_id:
            if project_id not in accessible_project_ids:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            target_pids = [project_id]
        else:
            target_pids = accessible_project_ids

        if not target_pids:
            # User has no assigned projects: can only see events where they are the actor
            conditions.append(AuditEvent.actor_id == current_user.id)
        else:
            str_pids = [str(pid) for pid in target_pids]
            project_scope_filter = or_(
                AuditEvent.actor_id == current_user.id,
                (AuditEvent.entity_type == "project") & (AuditEvent.entity_id.in_(target_pids)),
                AuditEvent.payload["project_id"].astext.in_(str_pids),
                (AuditEvent.entity_type == "expense") & (
                    AuditEvent.entity_id.in_(
                        select(Expense.id).where(Expense.project_id.in_(target_pids))
                    )
                ),
                (AuditEvent.entity_type == "project_budget") & (
                    AuditEvent.entity_id.in_(
                        select(ProjectBudget.id).where(ProjectBudget.project_id.in_(target_pids))
                    )
                ),
            )
            conditions.append(project_scope_filter)
    else:
        # System Admin: global access, with optional project_id filtering
        if project_id:
            str_pid = str(project_id)
            admin_project_filter = or_(
                (AuditEvent.entity_type == "project") & (AuditEvent.entity_id == project_id),
                AuditEvent.payload["project_id"].astext == str_pid,
                (AuditEvent.entity_type == "expense") & (
                    AuditEvent.entity_id.in_(
                        select(Expense.id).where(Expense.project_id == project_id)
                    )
                ),
                (AuditEvent.entity_type == "project_budget") & (
                    AuditEvent.entity_id.in_(
                        select(ProjectBudget.id).where(ProjectBudget.project_id == project_id)
                    )
                ),
            )
            conditions.append(admin_project_filter)

    base_query = select(AuditEvent)
    if conditions:
        base_query = base_query.where(*conditions)

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size
    data_query = base_query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(data_query)
    events = result.scalars().all()

    return {
        "items": [AuditEventResponse.model_validate(e) for e in events],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
