"""Staging schemas for human review workflow."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StagedExpenseItem(BaseModel):
    """Single staged expense item for review."""

    expense_id: UUID
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    transaction_date: str | None = None
    invoice_number: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    currency: str = "INR"
    payment_method: str | None = None
    confidence_score: float
    extraction_result: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


class StagingRequest(BaseModel):
    """Request to stage expenses for review."""

    expense_ids: list[UUID]
    reviewer_id: UUID | None = None
    notes: str | None = None


class StagingResponse(BaseModel):
    """Response after staging expenses."""

    staged_count: int
    message: str
    staged_expenses: list[StagedExpenseItem]


class StageActionRequest(BaseModel):
    """Request to approve/reject staged expense."""

    action: str = Field(pattern="^(approve|reject|request_changes)$")
    reviewer_id: UUID | None = None
    notes: str | None = None
    corrections: dict[str, Any] | None = None


class StageActionResponse(BaseModel):
    """Response after stage action."""

    expense_id: UUID
    action: str
    new_status: str
    message: str


class StagedExpenseDetail(BaseModel):
    """Detailed staged expense for review UI."""

    expense_id: UUID
    project_id: UUID
    project_name: str | None = None
    source_event_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    transaction_date: str | None = None
    invoice_number: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    currency: str = "INR"
    payment_method: str | None = None
    cgst_amount: float | None = None
    sgst_amount: float | None = None
    igst_amount: float | None = None
    hsn_sac_code: str | None = None
    irn: str | None = None
    confidence_score: float
    extraction_result: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    staged_at: datetime
    staged_by: UUID | None = None
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StagedListResponse(BaseModel):
    """Paginated staged expenses list."""

    items: list[StagedExpenseDetail]
    total: int
    page: int
    page_size: int


class StagingStats(BaseModel):
    """Staging statistics."""

    pending_review: int
    approved: int
    rejected: int
    changes_requested: int
    total_staged: int
