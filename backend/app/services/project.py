from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from app.models.project_member import ProjectMember
from app.repositories.project import ProjectRepository

if TYPE_CHECKING:
    from app.models.project_budget import ProjectBudget


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProjectRepository(session)

    async def create_project(
        self,
        name: str,
        code: str,
        created_by: UUID,
        status: str = "active",
    ) -> Project:
        existing = await self.repo.get_by_code(code)
        if existing:
            raise ValueError(f"Project with code '{code}' already exists")

        project = await self.repo.create(
            name=name,
            code=code,
            created_by=created_by,
            status=status,
        )
        return project

    async def get_project(self, project_id: UUID) -> Project | None:
        return await self.repo.get_by_id(project_id)

    async def list_projects(
        self,
        status_filter: str | None = None,
        project_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        return await self.repo.list_projects(
            status_filter=status_filter,
            project_ids=project_ids,
            limit=limit,
            offset=offset,
        )

    async def get_project_count(
        self,
        status_filter: str | None = None,
        project_ids: list[UUID] | None = None,
    ) -> int:
        return await self.repo.count(status_filter=status_filter, project_ids=project_ids)

    async def update_project(
        self,
        project_id: UUID,
        name: str | None = None,
        status: str | None = None,
    ) -> Project | None:
        project = await self.repo.get_by_id(project_id)
        if not project:
            return None

        if name is not None:
            project.name = name
        if status is not None:
            project.status = ProjectStatus(status)

        return await self.repo.update(project)

    async def delete_project(self, project_id: UUID) -> bool:
        project = await self.repo.get_by_id(project_id)
        if not project:
            return False
        await self.repo.delete(project)
        return True

    async def get_budget_vs_actual(self, project_id: UUID) -> dict:
        return await self.repo.get_budget_vs_actual(project_id)

    async def set_budget(
        self,
        project_id: UUID,
        amount: Decimal,
        currency: str = "INR",
        category_id: UUID | None = None,
        effective_from: str | None = None,
        effective_to: str | None = None,
    ) -> "ProjectBudget":
        from datetime import date

        from app.models.project_budget import ProjectBudget

        project = await self.repo.get_by_id(project_id)
        if not project:
            raise ValueError("Project not found")

        budget = ProjectBudget(
            project_id=project_id,
            category_id=category_id,
            amount=amount,
            currency=currency,
            effective_from=date.fromisoformat(effective_from) if effective_from else date.today(),
            effective_to=date.fromisoformat(effective_to) if effective_to else None,
        )
        self.session.add(budget)
        await self.session.flush()
        return budget

    async def get_budgets(self, project_id: UUID) -> list["ProjectBudget"]:
        from app.models.project_budget import ProjectBudget

        result = await self.session.execute(
            select(ProjectBudget).where(ProjectBudget.project_id == project_id)
        )
        return list(result.scalars().all())

    async def add_member(
        self,
        project_id: UUID,
        user_id: UUID,
        role: str = "site_user",
    ) -> ProjectMember:
        """Add or update a project member."""
        result = await self.session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            member.role = role
        else:
            member = ProjectMember(
                project_id=project_id,
                user_id=user_id,
                role=role,
            )
            self.session.add(member)
        await self.session.flush()
        return member

    async def remove_member(self, project_id: UUID, user_id: UUID) -> bool:
        """Remove a user from project members."""
        result = await self.session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        await self.session.delete(member)
        await self.session.flush()
        return True

    async def list_members(self, project_id: UUID) -> list[ProjectMember]:
        """List all members of a project."""
        result = await self.session.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
        return list(result.scalars().all())
