"""Posting schemas for ledger integration."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LedgerEntryCreate(BaseModel):
    """Create a single ledger entry."""

    ledger_account_id: UUID
    amount: Decimal = Field(gt=0)
    entry_type: str = Field(pattern="^(DEBIT|CREDIT)$")
    description: str | None = None


class PostingRequest(BaseModel):
    """Request to post a reconciled expense to ledger."""

    expense_id: UUID
    description: str | None = None
    custom_entries: list[LedgerEntryCreate] | None = None


class PostingResponse(BaseModel):
    """Response after posting to ledger."""

    expense_id: UUID
    status: str
    ledger_entries: list["LedgerEntryResponse"]
    message: str


class LedgerEntryResponse(BaseModel):
    """Ledger entry response."""

    id: UUID
    ledger_account_id: UUID
    ledger_account_name: str | None = None
    ledger_account_type: str | None = None
    expense_id: UUID | None = None
    amount: Decimal
    entry_type: str
    posted_at: datetime
    source_audit_event_id: UUID | None = None
    description: str | None = None
    is_reversal: bool = False

    model_config = ConfigDict(from_attributes=True)


class ReversalRequest(BaseModel):
    """Request to reverse an existing expense posting."""

    expense_id: UUID
    reason: str | None = None


class ReversalResponse(BaseModel):
    """Response after reversing a posting."""

    expense_id: UUID
    status: str
    message: str
    ledger_entries: list[LedgerEntryResponse]


class PostingDetailResponse(BaseModel):
    """Detailed posting with expense and payment info."""

    expense_id: UUID
    expense_vendor: str | None = None
    expense_amount: Decimal
    expense_date: str | None = None
    payment_amount: Decimal | None = None
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool
    ledger_entries: list[LedgerEntryResponse]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostingListResponse(BaseModel):
    """Paginated posting list."""

    items: list[PostingDetailResponse]
    total: int
    page: int
    page_size: int


class AccountBalanceResponse(BaseModel):
    """Account balance response."""

    ledger_account_id: UUID
    account_name: str
    account_type: str
    currency: str
    current_balance: Decimal
    last_posted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AccountBalanceListResponse(BaseModel):
    """List of account balances."""

    items: list[AccountBalanceResponse]
    total: int
    page: int
    page_size: int


class TrialBalanceResponse(BaseModel):
    """Trial balance for a project."""

    project_id: UUID | None = None
    as_of_date: datetime
    accounts: list[AccountBalanceResponse]
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool
