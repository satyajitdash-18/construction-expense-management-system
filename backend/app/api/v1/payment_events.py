from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import PaymentMethod
from app.models.payment_event import PaymentEvent
from app.models.source_event import SourceEvent

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/payment-events", tags=["payment-events"])


class PaymentEventCreate(BaseModel):
    amount: Decimal
    currency: str = "INR"
    occurred_at: datetime = Field(default_factory=datetime.now)
    payee_raw_text: str = "Payment"
    payment_method: str = "BANK_TRANSFER"
    reference_number: str | None = None
    upi_reference: str | None = None
    bank_reference: str | None = None
    raw_text: str = "Payment event"
    idempotency_key: str | None = None
    project_id: UUID | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def populate_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "occurred_at" not in data and "date" in data:
                data["occurred_at"] = data["date"]
            if "payee_raw_text" not in data and "payee" in data:
                data["payee_raw_text"] = data["payee"]
            if "reference_number" in data and not data.get("bank_reference"):
                data["bank_reference"] = data["reference_number"]
            if not data.get("idempotency_key"):
                data["idempotency_key"] = str(uuid4())
        return data


class PaymentEventResponse(BaseModel):
    id: UUID
    amount: Decimal
    occurred_at: datetime
    payee_raw_text: str
    payment_method: str
    bank_reference: str | None = None
    upi_reference: str | None = None
    idempotency_key: str

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=PaymentEventResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_event(
    request: PaymentEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
) -> PaymentEventResponse:
    from app.models.enums import PaymentMethod, SourceType


    source_event = SourceEvent(
        source=SourceType.SMS_UPI,
        idempotency_key=request.idempotency_key or str(uuid4()),
        raw_payload={"amount": float(request.amount)},
    )

    db.add(source_event)
    await db.flush()

    # Normalize payment method
    try:
        method = PaymentMethod(request.payment_method)
    except Exception:
        method = PaymentMethod.BANK_TRANSFER

    payment_event = PaymentEvent(
        source_event_id=source_event.id,
        amount=request.amount,
        occurred_at=request.occurred_at,
        payee_raw_text=request.payee_raw_text,
        payment_method=method,
        bank_reference=request.bank_reference or request.reference_number,
        upi_reference=request.upi_reference,
        raw_text=request.raw_text,
        idempotency_key=request.idempotency_key or str(uuid4()),
    )
    db.add(payment_event)
    await db.commit()
    await db.refresh(payment_event)

    return PaymentEventResponse.model_validate(payment_event)
