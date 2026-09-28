"""Audit compliance schemas for audit trail, reports, and data retention."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditEventFilter(BaseModel):
    """Filter for querying audit events."""

    entity_type: str | None = None
    entity_id: UUID | None = None
    event_type: str | None = None
    actor_id: UUID | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class AuditEventResponse(BaseModel):
    """Audit event response with full details."""

    id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID
    actor_id: UUID | None = None
    correlation_id: UUID
    causation_id: UUID | None = None
    payload: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditEventListResponse(BaseModel):
    """Paginated audit event list."""

    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int


class AuditTrailResponse(BaseModel):
    """Complete audit trail for an entity."""

    entity_type: str
    entity_id: UUID
    events: list[AuditEventResponse]
    total_events: int
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None


from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuditReportRequest(BaseModel):
    """Request to generate an audit report."""

    report_type: str = Field(pattern="^(?i)(entity_trail|user_activity|system_changes|data_access|compliance_summary|expense_summary)$")
    entity_type: str | None = None
    entity_id: UUID | None = None
    user_id: UUID | None = None
    date_from: datetime = Field(default_factory=lambda: datetime(2020, 1, 1))
    date_to: datetime = Field(default_factory=lambda: datetime.now())
    format: str = Field(default="json", pattern="^(?i)(json|csv|pdf)$")
    include_payload: bool = True

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_request(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "format" in data and isinstance(data["format"], str):
                data["format"] = data["format"].lower()
            if "report_type" in data and isinstance(data["report_type"], str):
                data["report_type"] = data["report_type"].lower()
            if "filters" in data and isinstance(data["filters"], dict):
                filters = data["filters"]
                if "date_from" in filters and "date_from" not in data:
                    data["date_from"] = filters["date_from"]
                if "date_to" in filters and "date_to" not in data:
                    data["date_to"] = filters["date_to"]
                if "entity_type" in filters and "entity_type" not in data:
                    data["entity_type"] = filters["entity_type"]
        return data



class AuditReportResponse(BaseModel):
    """Generated audit report response."""

    report_id: UUID
    report_type: str
    status: str = Field(pattern="^(generating|completed|failed)$")
    download_url: str | None = None
    generated_at: datetime | None = None
    expires_at: datetime | None = None
    record_count: int = 0
    file_size_bytes: int | None = None


class DataRetentionPolicyCreate(BaseModel):
    """Create a data retention policy."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    entity_types: list[str] = Field(min_length=1)
    retention_days: int = Field(gt=0)
    archive_after_days: int | None = None
    delete_after_days: int | None = None
    is_active: bool = True


class DataRetentionPolicyResponse(BaseModel):
    """Data retention policy response."""

    id: UUID
    name: str
    description: str | None = None
    entity_types: list[str]
    retention_days: int
    archive_after_days: int | None = None
    delete_after_days: int | None = None
    is_active: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DataRetentionPolicyListResponse(BaseModel):
    """Paginated data retention policy list."""

    items: list[DataRetentionPolicyResponse]
    total: int
    page: int
    page_size: int


class GDPRRequestCreate(BaseModel):
    """Create a GDPR data subject request."""

    request_type: str = Field(pattern="^(access|rectification|erasure|portability|restriction|objection)$")
    user_id: UUID
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    description: str | None = None
    verification_token: str | None = None


class GDPRRequestResponse(BaseModel):
    """GDPR request response."""

    id: UUID
    request_type: str
    user_id: UUID
    email: str
    status: str = Field(pattern="^(pending|processing|completed|rejected)$")
    description: str | None = None
    response_data: dict[str, Any] | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class GDPRRequestListResponse(BaseModel):
    """Paginated GDPR request list."""

    items: list[GDPRRequestResponse]
    total: int
    page: int
    page_size: int


class ComplianceDashboardResponse(BaseModel):
    """Compliance dashboard overview."""

    audit_events_today: int
    audit_events_this_month: int
    pending_gdpr_requests: int
    completed_gdpr_requests_this_month: int
    data_retention_policies_active: int
    records_archived_this_month: int
    records_deleted_this_month: int
    audit_reports_generated_this_month: int
    failed_webhook_deliveries: int
