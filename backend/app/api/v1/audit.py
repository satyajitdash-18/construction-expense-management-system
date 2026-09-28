"""Lightweight /audit/logs endpoint alias for backwards compatibility."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_db_dep
from app.core.dependencies import get_current_user as get_current_user_dep
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=dict)
async def list_audit_logs(
    entity_type: str | None = Query(None),
    entity_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict[str, Any]:
    """List audit log events with optional filtering."""
    from sqlalchemy import func, select

    from app.models.audit_event import AuditEvent

    conditions = []
    if entity_type:
        conditions.append(AuditEvent.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditEvent.entity_id == entity_id)

    # Count
    base_query = select(AuditEvent)
    if conditions:
        base_query = base_query.where(*conditions)

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    data_query = base_query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(data_query)
    events = result.scalars().all()

    from app.schemas.audit_compliance import AuditEventResponse

    return {
        "items": [AuditEventResponse.model_validate(e) for e in events],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
