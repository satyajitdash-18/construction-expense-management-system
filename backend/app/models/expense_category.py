from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    parent_category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    parent_category: Mapped["ExpenseCategory | None"] = relationship(
        remote_side="ExpenseCategory.id", backref="subcategories", lazy="selectin"
    )
    expenses: Mapped[list["Expense"]] = relationship(back_populates="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<ExpenseCategory(id={self.id}, name={self.name})>"
