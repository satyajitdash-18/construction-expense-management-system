"""OCR schemas for text extraction."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OCRLine(BaseModel):
    """Single line of OCR output."""

    text: str
    confidence: int
    bbox: dict[str, int]
    line_num: int
    block_num: int


class OCRResult(BaseModel):
    """OCR extraction result."""

    full_text: str
    avg_confidence: float
    lines: list[OCRLine]
    word_count: int


class OCRProcessRequest(BaseModel):
    """Request to process OCR on evidence."""

    evidence_id: UUID
    language: str | None = None
    preprocessing_options: dict[str, Any] | None = None


class OCRProcessResponse(BaseModel):
    """Response after OCR processing."""

    job_id: UUID
    status: str
    message: str


class OCRJobStatus(BaseModel):
    """OCR job status response."""

    id: UUID
    source_event_id: UUID | None = None
    status: str
    result: dict[str, Any] | OCRResult | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OCRJobListResponse(BaseModel):
    """Paginated OCR job list."""

    items: list[OCRJobStatus]
    total: int
    page: int
    page_size: int
