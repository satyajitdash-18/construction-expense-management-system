from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, cast, func, select
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import LifecycleStatus as LifecycleStatusEnum
from app.models.expense import Expense
from app.models.project import Project
from app.models.project_budget import ProjectBudget
from app.models.project_member import ProjectMember

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.project_budget import ProjectBudget


# Create the enum type for casting
lifecycle_status_pg_enum = ENUM(
    *[s.value for s in LifecycleStatusEnum],
    name="lifecyclestatus",
    create_type=False
)


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, project_id: UUID) -> Project | None:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.budgets), selectinload(Project.ledger_accounts))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.code == code)
        )
        return result.scalar_one_or_none()

    async def list_projects(
        self,
        status_filter: str | None = None,
        project_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        query = select(Project).options(selectinload(Project.budgets))
        if status_filter:
            query = query.where(Project.status == status_filter)
        if project_ids is not None:
            query = query.where(Project.id.in_(project_ids))
        query = query.order_by(Project.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        status_filter: str | None = None,
        project_ids: list[UUID] | None = None,
    ) -> int:
        query = select(func.count(Project.id))
        if status_filter:
            query = query.where(Project.status == status_filter)
        if project_ids is not None:
            query = query.where(Project.id.in_(project_ids))
        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(
        self,
        name: str,
        code: str,
        created_by: UUID,
        status: str = "active",
    ) -> Project:
        project = Project(
            name=name,
            code=code,
            created_by=created_by,
            status=status,
        )
        self.session.add(project)
        await self.session.flush()

        member = ProjectMember(
            project_id=project.id,
            user_id=created_by,
            role="project_manager",
        )
        self.session.add(member)
        await self.session.flush()

        return project

    async def update(self, project: Project) -> Project:
        await self.session.flush()
        return project

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)
        await self.session.flush()

    async def get_budget_vs_actual(self, project_id: UUID) -> dict:
        """Get budget vs actual for a project."""
        project = await self.get_by_id(project_id)
        if not project:
            return {}

        # Get all budgets for the project
        budgets_result = await self.session.execute(
            select(ProjectBudget).where(ProjectBudget.project_id == project_id)
        )
        budgets = list(budgets_result.scalars().all())

        # Get actual expenses (only POSTED/RECONCILED)
        expenses_result = await self.session.execute(
            select(
                Expense.category_id,
                func.sum(Expense.total).label("actual_total"),
            )
            .where(
                and_(
                    Expense.project_id == project_id,
                    cast(Expense.lifecycle_status, lifecycle_status_pg_enum).in_(
                        [LifecycleStatusEnum.POSTED, LifecycleStatusEnum.RECONCILED]
                    ),
                )
            )
            .group_by(Expense.category_id)
        )
        actuals = {row.category_id: row.actual_total for row in expenses_result.all()}

        # Build budget vs actual
        budget_vs_actual: list[dict] = []
        total_budget: Decimal = Decimal("0.00")
        total_actual: Decimal = Decimal("0.00")

        for budget in budgets:
            actual = actuals.get(budget.category_id, Decimal("0.00")) or Decimal("0.00")
            b_amount = Decimal(str(budget.amount))
            act_amount = Decimal(str(actual))
            var_amount = b_amount - act_amount
            budget_vs_actual.append({
                "category_id": str(budget.category_id) if budget.category_id else None,
                "budget": b_amount,
                "actual": act_amount,
                "variance": var_amount,
                "currency": budget.currency,
                "effective_from": budget.effective_from.isoformat() if budget.effective_from else None,
                "effective_to": budget.effective_to.isoformat() if budget.effective_to else None,
            })
            total_budget += b_amount
            total_actual += act_amount

        # Add overall project budget (category_id is None)
        overall_budget = next((b for b in budgets if b.category_id is None), None)
        if overall_budget:
            total_budget = Decimal(str(overall_budget.amount))
            # Recalculate actuals for overall
            total_expenses_result = await self.session.execute(
                select(func.sum(Expense.total))
                .where(
                    and_(
                        Expense.project_id == project_id,
                        cast(Expense.lifecycle_status, lifecycle_status_pg_enum).in_(
                            [LifecycleStatusEnum.POSTED, LifecycleStatusEnum.RECONCILED]
                        ),
                    )
                )
            )
            total_actual = Decimal(str(total_expenses_result.scalar_one_or_none() or "0.00"))

        return {
            "project_id": str(project_id),
            "total_budget": total_budget,
            "total_actual": total_actual,
            "remaining": total_budget - total_actual,
            "by_category": budget_vs_actual,
        }
