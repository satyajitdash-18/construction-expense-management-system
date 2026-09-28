"""Reconciliation schemas for expense-payment matching."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReconciliationCandidate(BaseModel):
    """Candidate payment event for reconciliation."""

    payment_event_id: UUID
    amount: float
    occurred_at: str
    payee_raw_text: str
    upi_reference: str | None = None
    bank_reference: str | None = None
    payment_method: str
    match_score: float
    match_basis: str


class ReconciliationRequest(BaseModel):
    """Request to reconcile an expense."""

    expense_id: UUID
    payment_event_id: UUID | None = None
    auto_match: bool = True
    confidence_threshold: float = 0.8


class ReconciliationActionRequest(BaseModel):
    """Request to confirm/reject a reconciliation."""

    action: str = Field(pattern="^(confirm|reject|unmatch)$")
    reviewer_id: UUID | None = None
    notes: str | None = None
    match_basis: str | None = None
    reconciliation_id: UUID | None = None


class ReconciliationRecordResponse(BaseModel):
    """Reconciliation record response."""

    id: UUID
    expense_id: UUID
    payment_event_id: UUID | None
    status: str
    match_basis: str | None
    match_score: float | None
    resolved_by: UUID | None
    resolution_reason: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ReconciliationDetailResponse(BaseModel):
    """Detailed reconciliation with expense and payment info."""

    id: UUID
    expense_id: UUID
    expense_vendor: str | None = None
    expense_amount: float
    expense_date: str | None = None
    payment_event_id: UUID | None
    payment_amount: float | None = None
    payment_date: str | None = None
    payment_payee: str | None = None
    payment_upi_ref: str | None = None
    payment_bank_ref: str | None = None
    status: str
    match_basis: str | None
    match_score: float | None
    resolved_by: UUID | None
    resolution_reason: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ReconciliationListResponse(BaseModel):
    """Paginated reconciliation list."""

    items: list[ReconciliationDetailResponse]
    total: int
    page: int
    page_size: int


class ReconciliationStats(BaseModel):
    """Reconciliation statistics."""

    total: int
    matched: int
    unmatched: int
    ambiguous: int
    manually_resolved: int
    pending_auto_match: int


class AutoMatchRequest(BaseModel):
    """Request to run auto-matching."""

    project_id: UUID | None = None
    date_from: str | None = None
    date_to: str | None = None
    confidence_threshold: float = 0.8
    dry_run: bool = False


class AutoMatchResult(BaseModel):
    """Result of auto-matching run."""

    processed: int
    matched: int
    ambiguous: int
    unmatched: int
    errors: int
    matches: list[dict[str, Any]] = Field(default_factory=list)
