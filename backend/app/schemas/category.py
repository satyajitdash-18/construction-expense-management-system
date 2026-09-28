from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class ExpenseCategoryCreate(BaseModel):
    name: str
    parent_category_id: UUID | None = None


class ExpenseCategoryUpdate(BaseModel):
    name: str | None = None
    parent_category_id: UUID | None = None


class ExpenseCategoryResponse(BaseModel):
    id: UUID
    name: str
    parent_category_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None
