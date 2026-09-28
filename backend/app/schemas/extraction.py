"""Extraction schemas for LLM-based expense extraction."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LineItemExtraction(BaseModel):
    """Extracted line item."""

    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float
    tax_amount: float | None = None


class ExtractionRequest(BaseModel):
    """Request to run LLM extraction."""

    evidence_id: UUID
    provider: str | None = None
    use_cached_ocr: bool = True


class ExtractionResponse(BaseModel):
    """LLM extraction result."""

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
    line_items: list[LineItemExtraction] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    raw_response: str | None = None


class ExtractionProcessResponse(BaseModel):
    """Response after starting extraction."""

    job_id: UUID
    status: str
    message: str


class ExtractionJobStatus(BaseModel):
    """Extraction job status."""

    id: UUID
    source_event_id: UUID | None
    status: str
    result: ExtractionResponse | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ExtractionJobListResponse(BaseModel):
    """Paginated extraction job list."""

    items: list[ExtractionJobStatus]
    total: int
    page: int
    page_size: int


class ExtractionValidationResult(BaseModel):
    """Validation result for extracted data."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence_adjustment: float = 0.0
