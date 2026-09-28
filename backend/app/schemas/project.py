from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer

if TYPE_CHECKING:
    pass


class ProjectBase(BaseModel):
    name: str
    code: str
    status: str = "active"

    model_config = ConfigDict(extra="ignore")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    status: str | None = None

    model_config = ConfigDict(extra="ignore")


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    code: str
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    @field_serializer('created_at')
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer('updated_at')
    def serialize_updated_at(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int
    page: int = 1
    page_size: int = 50
    size: int = 50



class BudgetCreate(BaseModel):
    amount: float
    currency: str = "INR"
    # Accept either category_id (UUID) or category (string name)
    category_id: UUID | None = None
    category: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    # Accept project_id at body level (for standalone /budgets endpoint)
    project_id: UUID | None = None


class BudgetResponse(BaseModel):
    id: UUID
    project_id: UUID
    category_id: UUID | None = None
    amount: float
    currency: str
    effective_from: date
    effective_to: date | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('created_at')
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer('effective_from')
    def serialize_effective_from(self, value: date) -> str:
        return value.isoformat()

    @field_serializer('effective_to')
    def serialize_effective_to(self, value: date | None) -> str | None:
        return value.isoformat() if value else None


class BudgetVsActualResponse(BaseModel):
    project_id: UUID
    total_budget: float
    total_actual: float
    remaining: float
    by_category: list[dict]
    currency: str = "INR"

    # Aliases for API consumers that use 'budget', 'actual', 'variance' keys
    @property
    def budget(self) -> float:
        return self.total_budget

    @property
    def actual(self) -> float:
        return self.total_actual

    @property
    def variance(self) -> float:
        return self.remaining

    model_config = ConfigDict(from_attributes=True)
