from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class VendorCreate(BaseModel):
    name: str
    gstin: str | None = None
    phone: str | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="ignore")


class VendorUpdate(BaseModel):
    name: str | None = None
    gstin: str | None = None
    phone: str | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="ignore")



class VendorResponse(BaseModel):
    id: UUID
    name: str
    gstin: str | None = None
    phone: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


class VendorListResponse(BaseModel):
    items: list[VendorResponse]
    total: int
    page: int = 1
    page_size: int = 50
    limit: int | None = None
    offset: int | None = None

