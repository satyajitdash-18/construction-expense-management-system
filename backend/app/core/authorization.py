"""Centralized authorization and project scoping security module."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User


async def get_project_member_role(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
) -> str | None:
    """Return user's explicit role on the project, or None if not an explicit member."""
    result = await db.execute(
        select(ProjectMember.role).where(
            ProjectMember.user_id == user_id,
            ProjectMember.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def verify_project_access(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    allowed_roles: Sequence[str] | None = None,
) -> Project:
    """
    Verify that `user` is authorized to access `project_id`.

    Authorization rules:
    1. System 'admin' has universal access to all projects for any operation.
    2. The project creator (project.created_by == user.id) has full project access.
    3. If user is in `project_members`, their project member role (or system role) is verified:
       - If `allowed_roles` is None: any valid project member has access.
       - If `allowed_roles` is provided: user's member role OR user's system role must intersect `allowed_roles`.
    4. If not authorized, raises 403 Forbidden.
    5. If project does not exist, raises 404 Not Found.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    user_system_roles = {r.name for r in user.roles}
    if "admin" in user_system_roles:
        return project

    is_creator = project.created_by == user.id
    member_role = await get_project_member_role(db, user.id, project_id)

    if not is_creator and member_role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    if allowed_roles:
        # Check if project member role or system role matches allowed roles
        user_effective_roles = set(user_system_roles)
        if member_role:
            user_effective_roles.add(member_role)
        if is_creator:
            user_effective_roles.add("project_manager")

        if not user_effective_roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for this project. Required roles: {', '.join(allowed_roles)}",
            )

    return project


async def get_user_accessible_project_ids(
    db: AsyncSession,
    user: User,
) -> list[UUID] | None:
    """
    Return list of project IDs the user has access to.
    If user is system admin, returns None (meaning all projects are accessible).
    """
    user_system_roles = {r.name for r in user.roles}
    if "admin" in user_system_roles:
        return None

    result = await db.execute(
        select(Project.id)
        .outerjoin(ProjectMember, Project.id == ProjectMember.project_id)
        .where(
            or_(
                Project.created_by == user.id,
                ProjectMember.user_id == user.id,
            )
        )
        .distinct()
    )
    return list(result.scalars().all())


def require_project_access(allowed_roles: Sequence[str] | None = None):
    """FastAPI dependency factory to enforce project scoping."""
    async def _dependency(
        project_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Project:
        return await verify_project_access(db, current_user, project_id, allowed_roles)

    return _dependency
