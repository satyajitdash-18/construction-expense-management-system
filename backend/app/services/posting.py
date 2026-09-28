"""Posting service for double-entry accounting."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.helper import write_audit_event
from app.core.logging import get_logger
from app.models.enums import AccountType, EntryType, LifecycleStatus
from app.models.expense import Expense
from app.models.ledger import LedgerAccount, LedgerEntry

logger = get_logger(__name__)


class PostingService:
    """Service for posting reconciled expenses to ledger (double-entry accounting)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_default_accounts(self, project_id: UUID) -> dict[AccountType, LedgerAccount]:
        """Get or create default ledger accounts for a project."""
        # Get existing accounts
        result = await self.db.execute(
            select(LedgerAccount).where(LedgerAccount.project_id == project_id)
        )
        accounts = {acc.account_type: acc for acc in result.scalars().all()}

        # Create missing default accounts if needed
        defaults = {
            AccountType.EXPENSE: {"name": "Expenses", "account_type": AccountType.EXPENSE},
            AccountType.ASSET: {"name": "Cash/Bank", "account_type": AccountType.ASSET},
            AccountType.LIABILITY: {"name": "Accounts Payable", "account_type": AccountType.LIABILITY},
        }

        for acc_type, default in defaults.items():
            if acc_type not in accounts:
                account = LedgerAccount(
                    project_id=project_id,
                    name=default["name"],
                    account_type=default["account_type"],
                    currency="INR",
                )
                self.db.add(account)
                await self.db.flush()
                accounts[acc_type] = account

        return accounts

    async def post_expense(
        self,
        expense_id: UUID,
        actor_id: UUID | None = None,
        description: str | None = None,
        custom_entries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Post a reconciled expense to the ledger (double-entry accounting).

        Standard posting for Indian construction expenses:
        - Debit: Expense account (P&L)
        - Credit: Accounts Payable (Liability) or Cash/Bank (Asset)

        For GST invoices:
        - Debit: Expense (net amount)
        - Debit: Input CGST (Asset - recoverable)
        - Debit: Input SGST (Asset - recoverable)
        - Debit: Input IGST (Asset - recoverable)
        - Credit: Accounts Payable / Cash / Bank
        """
        expense = await self.db.get(Expense, expense_id)
        if not expense:
            raise ValueError(f"Expense {expense_id} not found")

        if expense.lifecycle_status not in [LifecycleStatus.RECONCILED, LifecycleStatus.POSTED]:
            raise ValueError(f"Expense must be RECONCILED or POSTED, current: {expense.lifecycle_status}")

        # Check if already posted
        existing = await self.db.execute(
            select(LedgerEntry).where(
                LedgerEntry.expense_id == expense_id,
                LedgerEntry.source_audit_event_id.is_not(None),
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Expense {expense_id} already posted to ledger")

        # Get or create default accounts
        accounts = await self.get_default_accounts(expense.project_id)

        entries = []

        if custom_entries:
            # Use custom entries provided by user
            for entry_data in custom_entries:
                entry = LedgerEntry(
                    ledger_account_id=entry_data["ledger_account_id"],
                    expense_id=expense_id,
                    amount=entry_data["amount"],
                    entry_type=EntryType(entry_data["entry_type"]),
                    posted_at=datetime.now(UTC),
                    source_audit_event_id=None,  # Will be set after audit event
                    description=entry_data.get("description"),
                )
                entries.append(entry)
        else:
            # Standard posting for Indian construction expense
            expense_account = accounts[AccountType.EXPENSE]

            # Determine credit account based on payment method
            if expense.payment_method in ["CASH", "BANK_TRANSFER", "UPI"]:
                credit_account = accounts[AccountType.ASSET]
            else:
                credit_account = accounts[AccountType.LIABILITY]

            # Handle GST breakdown if present
            if expense.cgst_amount and expense.cgst_amount > 0:
                # CGST recoverable
                cgst_account = await self._get_or_create_tax_account(
                    expense.project_id, "Input CGST", AccountType.ASSET
                )
                entries.append(LedgerEntry(
                    ledger_account_id=cgst_account.id,
                    expense_id=expense_id,
                    amount=expense.cgst_amount,
                    entry_type=EntryType.DEBIT,
                    posted_at=datetime.now(UTC),
                    source_audit_event_id=None,
                    description=f"Input CGST - {expense.vendor.name if expense.vendor else 'Vendor'}",
                ))

            if expense.sgst_amount and expense.sgst_amount > 0:
                # SGST recoverable
                sgst_account = await self._get_or_create_tax_account(
                    expense.project_id, "Input SGST", AccountType.ASSET
                )
                entries.append(LedgerEntry(
                    ledger_account_id=sgst_account.id,
                    expense_id=expense_id,
                    amount=expense.sgst_amount,
                    entry_type=EntryType.DEBIT,
                    posted_at=datetime.now(UTC),
                    source_audit_event_id=None,
                    description=f"Input SGST - {expense.vendor.name if expense.vendor else 'Vendor'}",
                ))

            if expense.igst_amount and expense.igst_amount > 0:
                # IGST recoverable
                igst_account = await self._get_or_create_tax_account(
                    expense.project_id, "Input IGST", AccountType.ASSET
                )
                entries.append(LedgerEntry(
                    ledger_account_id=igst_account.id,
                    expense_id=expense_id,
                    amount=expense.igst_amount,
                    entry_type=EntryType.DEBIT,
                    posted_at=datetime.now(UTC),
                    source_audit_event_id=None,
                    description=f"Input IGST - {expense.vendor.name if expense.vendor else 'Vendor'}",
                ))

            # Net expense amount (total - recoverable taxes)
            recoverable_tax = (expense.cgst_amount or 0) + (expense.sgst_amount or 0) + (expense.igst_amount or 0)
            net_expense = expense.total - recoverable_tax

            if net_expense > 0:
                entries.append(LedgerEntry(
                    ledger_account_id=expense_account.id,
                    expense_id=expense_id,
                    amount=net_expense,
                    entry_type=EntryType.DEBIT,
                    posted_at=datetime.now(UTC),
                    source_audit_event_id=None,
                    description=description or f"Expense - {expense.vendor.name if expense.vendor else 'Vendor'}",
                ))

            # Credit entry
            entries.append(LedgerEntry(
                ledger_account_id=credit_account.id,
                expense_id=expense_id,
                amount=expense.total,
                entry_type=EntryType.CREDIT,
                posted_at=datetime.now(UTC),
                source_audit_event_id=None,
                description=description or f"Payment to {expense.vendor.name if expense.vendor else 'Vendor'}",
            ))

        # Verify double-entry balancing invariant before persisting
        debit_total = sum(Decimal(str(e.amount)) for e in entries if e.entry_type == EntryType.DEBIT)
        credit_total = sum(Decimal(str(e.amount)) for e in entries if e.entry_type == EntryType.CREDIT)

        if debit_total != credit_total:
            raise ValueError(
                f"Double-entry ledger invariant violated: total debits ({debit_total}) must equal total credits ({credit_total})"
            )
        if debit_total <= 0:
            raise ValueError("Ledger entry amount must be greater than zero")

        # Create audit event for posting FIRST to satisfy non-null foreign key
        audit_event_id = await write_audit_event(
            session=self.db,
            event_type="expense.posted",
            entity_type="expense",
            entity_id=expense_id,
            actor_id=actor_id,
            payload={
                "total_amount": float(expense.total),
                "entry_count": len(entries),
                "debit_total": float(debit_total),
                "credit_total": float(credit_total),
            },
        )

        # Link entries to audit event and write to database
        for entry in entries:
            entry.source_audit_event_id = audit_event_id
            self.db.add(entry)

        await self.db.flush()

        # Update expense status
        expense.lifecycle_status = LifecycleStatus.POSTED
        expense.updated_at = datetime.now(UTC)

        await self.db.commit()

        return {
            "expense_id": expense_id,
            "status": "POSTED",
            "ledger_entries": [
                {
                    "id": e.id,
                    "ledger_account_id": e.ledger_account_id,
                    "amount": float(e.amount),
                    "entry_type": e.entry_type.value,
                    "posted_at": e.posted_at,
                }
                for e in entries
            ],
            "debit_total": float(debit_total),
            "credit_total": float(credit_total),
            "is_balanced": True,
            "audit_event_id": audit_event_id,
        }

    async def _get_or_create_tax_account(
        self,
        project_id: UUID,
        name: str,
        account_type: AccountType,
    ) -> LedgerAccount:
        """Get or create a tax account (CGST, SGST, IGST)."""
        result = await self.db.execute(
            select(LedgerAccount).where(
                LedgerAccount.project_id == project_id,
                LedgerAccount.name == name,
            )
        )
        account = result.scalars().first()

        if not account:
            account = LedgerAccount(
                project_id=project_id,
                name=name,
                account_type=account_type,
                currency="INR",
            )
            self.db.add(account)
            await self.db.flush()

        return account

    async def get_expense_posting(self, expense_id: UUID) -> dict[str, Any] | None:
        """Get posting details for an expense."""
        expense = await self.db.get(Expense, expense_id)
        if not expense:
            return None

        result = await self.db.execute(
            select(LedgerEntry).where(LedgerEntry.expense_id == expense_id)
        )
        entries = result.scalars().all()

        if not entries:
            return None

        entries_data = []
        for entry in entries:
            account = await self.db.get(LedgerAccount, entry.ledger_account_id)
            entries_data.append({
                "id": entry.id,
                "ledger_account_id": entry.ledger_account_id,
                "ledger_account_name": account.name if account else None,
                "ledger_account_type": account.account_type.value if account else None,
                "amount": float(entry.amount),
                "entry_type": entry.entry_type.value,
                "posted_at": entry.posted_at,
                "source_audit_event_id": entry.source_audit_event_id,
                "description": entry.description,
            })

        debit_total = sum(e.amount for e in entries if e.entry_type == EntryType.DEBIT)
        credit_total = sum(e.amount for e in entries if e.entry_type == EntryType.CREDIT)

        return {
            "expense_id": expense_id,
            "expense_vendor": expense.vendor.name if expense.vendor else None,
            "expense_amount": float(expense.total),
            "expense_date": expense.transaction_date.isoformat() if expense.transaction_date else None,
            "payment_amount": None,
            "total_debits": float(debit_total),
            "total_credits": float(credit_total),
            "is_balanced": debit_total == credit_total,
            "ledger_entries": entries_data,
            "created_at": min(e.posted_at for e in entries) if entries else None,
        }

    async def list_postings(
        self,
        page: int = 1,
        page_size: int = 20,
        project_id: UUID | None = None,
    ) -> dict[str, Any]:
        """List all posted expenses with pagination."""
        query = select(LedgerEntry).where(LedgerEntry.expense_id.is_not(None))

        if project_id:
            query = query.where(
                LedgerEntry.expense_id.in_(
                    select(Expense.id).where(Expense.project_id == project_id)
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(
            select(LedgerEntry.expense_id).distinct().where(LedgerEntry.expense_id.is_not(None)).subquery()
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate by expense
        expense_ids_query = select(LedgerEntry.expense_id).distinct().where(
            LedgerEntry.expense_id.is_not(None)
        )
        if project_id:
            expense_ids_query = expense_ids_query.where(
                LedgerEntry.expense_id.in_(
                    select(Expense.id).where(Expense.project_id == project_id)
                )
            )

        expense_ids_query = expense_ids_query.order_by(LedgerEntry.posted_at.desc()).offset((page - 1) * page_size).limit(page_size)
        expense_ids_result = await self.db.execute(expense_ids_query)
        expense_ids = [row[0] for row in expense_ids_result]

        items = []
        for exp_id in expense_ids:
            posting = await self.get_expense_posting(exp_id)
            if posting:
                items.append(posting)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_account_balances(
        self,
        project_id: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Get current account balances."""
        query = select(LedgerAccount)

        if project_id:
            query = query.where(LedgerAccount.project_id == project_id)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(LedgerAccount.account_type, LedgerAccount.name)

        result = await self.db.execute(query)
        accounts = result.scalars().all()

        items = []
        for account in accounts:
            # Calculate balance from ledger entries
            debit_result = await self.db.execute(
                select(func.sum(LedgerEntry.amount)).where(
                    LedgerEntry.ledger_account_id == account.id,
                    LedgerEntry.entry_type == EntryType.DEBIT,
                )
            )
            credit_result = await self.db.execute(
                select(func.sum(LedgerEntry.amount)).where(
                    LedgerEntry.ledger_account_id == account.id,
                    LedgerEntry.entry_type == EntryType.CREDIT,
                )
            )

            debit_total = debit_result.scalar() or Decimal("0")
            credit_total = credit_result.scalar() or Decimal("0")
            balance = debit_total - credit_total

            # Get last posted date
            last_posted_result = await self.db.execute(
                select(func.max(LedgerEntry.posted_at)).where(
                    LedgerEntry.ledger_account_id == account.id
                )
            )
            last_posted = last_posted_result.scalar()

            items.append({
                "ledger_account_id": account.id,
                "account_name": account.name,
                "account_type": account.account_type.value,
                "currency": account.currency,
                "current_balance": float(balance),
                "last_posted_at": last_posted,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_trial_balance(
        self,
        project_id: UUID | None = None,
        as_of_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate trial balance for a project."""
        if as_of_date is None:
            as_of_date = datetime.now(UTC)

        query = select(LedgerAccount)
        if project_id:
            query = query.where(LedgerAccount.project_id == project_id)

        result = await self.db.execute(query)
        accounts = result.scalars().all()

        accounts_data = []
        total_debits = Decimal("0")
        total_credits = Decimal("0")

        for account in accounts:
            # Get entries up to as_of_date
            entries_query = select(LedgerEntry).where(
                LedgerEntry.ledger_account_id == account.id,
                LedgerEntry.posted_at <= as_of_date,
            )
            entries_result = await self.db.execute(entries_query)
            entries = entries_result.scalars().all()

            debit_total = sum(e.amount for e in entries if e.entry_type == EntryType.DEBIT)
            credit_total = sum(e.amount for e in entries if e.entry_type == EntryType.CREDIT)
            balance = debit_total - credit_total

            if balance != 0 or debit_total > 0 or credit_total > 0:
                total_debits += debit_total
                total_credits += credit_total

                accounts_data.append({
                    "ledger_account_id": account.id,
                    "account_name": account.name,
                    "account_type": account.account_type.value,
                    "currency": account.currency,
                    "current_balance": float(balance),
                    "last_posted_at": None,  # Could add last posted date
                })

        return {
            "project_id": project_id,
            "as_of_date": as_of_date,
            "accounts": accounts_data,
            "total_debits": float(total_debits),
            "total_credits": float(total_credits),
            "is_balanced": total_debits == total_credits,
        }


def create_posting_service(db: AsyncSession) -> PostingService:
    """Factory for creating PostingService."""
    return PostingService(db)
