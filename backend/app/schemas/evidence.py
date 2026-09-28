"""Evidence schemas for object storage."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceUploadRequest(BaseModel):
    """Request to upload evidence file."""

    expense_id: UUID
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str | None = None
    metadata: dict[str, Any] | None = None


class EvidenceUploadResponse(BaseModel):
    """Response after evidence upload."""

    object_name: str
    checksum: str
    size: int
    content_type: str
    presigned_url: str
    expires_at: datetime


class EvidenceResponse(BaseModel):
    """Evidence file response."""

    id: UUID
    expense_id: UUID
    object_name: str
    file_name: str
    content_type: str
    size: int
    checksum: str
    metadata: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceListResponse(BaseModel):
    """Paginated evidence list response."""

    items: list[EvidenceResponse]
    total: int
    page: int
    page_size: int


class PresignedUrlRequest(BaseModel):
    """Request for presigned URL."""

    object_name: str
    expires_in_seconds: int = 3600
    method: str = "GET"


class PresignedUrlResponse(BaseModel):
    """Presigned URL response."""

    url: str
    expires_at: datetime
    method: str
