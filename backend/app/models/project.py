from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ProjectStatus

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.ledger_account import LedgerAccount
    from app.models.project_budget import ProjectBudget
    from app.models.user import User


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", create_constraint=True),
        nullable=False,
        default=ProjectStatus.ACTIVE,
        index=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    creator: Mapped["User"] = relationship(lazy="selectin")
    budgets: Mapped[list["ProjectBudget"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    expenses: Mapped[list["Expense"]] = relationship(back_populates="project", lazy="dynamic")
    ledger_accounts: Mapped[list["LedgerAccount"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name}, code={self.code}, status={self.status})>"
