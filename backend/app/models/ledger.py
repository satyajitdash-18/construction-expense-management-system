from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import AccountType, EntryType

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.project import Project


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type", create_constraint=True),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    project: Mapped["Project | None"] = relationship(back_populates="ledger_accounts", lazy="selectin")
    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="account", lazy="dynamic")

    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<LedgerAccount(id={self.id}, name={self.name}, type={self.account_type})>"


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    ledger_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    expense_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    entry_type: Mapped[EntryType] = mapped_column(
        Enum(EntryType, name="entry_type", create_constraint=True),
        nullable=False,
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_audit_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    account: Mapped["LedgerAccount"] = relationship(back_populates="entries", lazy="selectin")
    expense: Mapped["Expense | None"] = relationship(lazy="selectin")

    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<LedgerEntry(id={self.id}, account={self.ledger_account_id}, {self.entry_type}={self.amount})>"
