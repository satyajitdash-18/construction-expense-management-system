from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer, model_validator

from app.schemas.vendor import VendorResponse


class ExpenseLineItemCreate(BaseModel):
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal
    tax_amount: Decimal | None = None


class ExpenseLineItemResponse(BaseModel):
    id: UUID
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal
    tax_amount: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    project_id: UUID
    transaction_date: date | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total: Decimal
    currency: str = "INR"
    payment_method: str = "CASH"
    vendor_id: UUID | None = None
    category_id: UUID | None = None
    line_items: list[ExpenseLineItemCreate] | None = None
    vendor_name: str | None = None
    gstin_supplier: str | None = None
    hsn_sac_code: str | None = None
    cgst_amount: Decimal | None = None
    sgst_amount: Decimal | None = None
    igst_amount: Decimal | None = None
    irn: str | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def populate_defaults(cls, data: Any) -> Any:
        import re
        if isinstance(data, dict):
            if "transaction_date" not in data and "date" in data:
                data["transaction_date"] = data["date"]
            if not data.get("transaction_date"):
                data["transaction_date"] = date.today()
            total = data.get("total", 0)
            if "subtotal" not in data or data["subtotal"] is None:
                data["subtotal"] = total
            if "tax_amount" not in data or data["tax_amount"] is None:
                data["tax_amount"] = 0
            if "gstin_supplier" not in data and "vendor_gstin" in data:
                data["gstin_supplier"] = data["vendor_gstin"]

            # --- Validate non-negative Decimal values and financial balancing invariant ---
            try:
                dec_total = Decimal(str(data.get("total", 0)))
                if dec_total < Decimal("0"):
                    raise ValueError("total must be non-negative")
                dec_subtotal = Decimal(str(data.get("subtotal", dec_total)))
                if dec_subtotal < Decimal("0"):
                    raise ValueError("subtotal must be non-negative")
                dec_tax = Decimal(str(data.get("tax_amount", 0)))
                if dec_tax < Decimal("0"):
                    raise ValueError("tax_amount must be non-negative")

                if abs((dec_subtotal + dec_tax) - dec_total) > Decimal("0.05"):
                    if "tax_amount" not in data or data["tax_amount"] is None:
                        data["subtotal"] = dec_total
                        data["tax_amount"] = Decimal("0.00")
                    else:
                        raise ValueError(
                            f"Financial invariant violated: subtotal ({dec_subtotal}) + tax_amount ({dec_tax}) "
                            f"must equal total ({dec_total})"
                        )
            except (TypeError, ValueError) as e:
                if "must be non-negative" in str(e) or "Financial invariant" in str(e):
                    raise

            # --- Validate GSTIN format (15-char alphanumeric pattern) ---
            gstin = data.get("gstin_supplier") or data.get("vendor_gstin")
            if gstin:
                gstin_pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
                if not re.match(gstin_pattern, str(gstin)):
                    raise ValueError(
                        f"Invalid GSTIN format: '{gstin}'. "
                        "Must be 15 characters matching pattern: 2digits+5letters+4digits+letter+char+Z+char"
                    )
        return data



class ExpenseUpdate(BaseModel):
    transaction_date: date | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    payment_method: str | None = None
    vendor_id: UUID | None = None
    category_id: UUID | None = None
    vendor_name: str | None = None
    gstin_supplier: str | None = None
    hsn_sac_code: str | None = None
    cgst_amount: Decimal | None = None
    sgst_amount: Decimal | None = None
    igst_amount: Decimal | None = None
    irn: str | None = None
    lifecycle_status: str | None = None


class ExpenseResponse(BaseModel):
    id: UUID
    project_id: UUID
    source_event_id: UUID | None
    vendor_id: UUID | None
    category_id: UUID | None
    transaction_date: date
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    currency: str
    payment_method: str
    gstin_supplier: str | None
    hsn_sac_code: str | None
    cgst_amount: Decimal | None
    sgst_amount: Decimal | None
    igst_amount: Decimal | None
    irn: str | None
    confidence_score: Decimal | None
    lifecycle_status: str
    receipt_id: UUID | None
    source_audit_event_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None

    vendor: Optional["VendorResponse"] = None
    vendor_name: str | None = None

    # category: Optional["ExpenseCategoryResponse"] = None
    # project: Optional["ProjectResponse"] = None
    # receipt: "ReceiptResponse | None" = None
    line_items: list["ExpenseLineItemResponse"] = []

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("transaction_date")
    def serialize_transaction_date(self, value: date) -> str:
        return value.isoformat()

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse]
    total: int
    limit: int
    offset: int
    page: int = 1
    page_size: int = 50
    size: int = 50



class ExpenseTransitionRequest(BaseModel):
    new_status: str

    @model_validator(mode="before")
    @classmethod
    def normalise_status_field(cls, values: dict) -> dict:
        """Accept either 'new_status' or 'target_status' from callers."""
        if isinstance(values, dict) and "new_status" not in values and "target_status" in values:
            values["new_status"] = values.pop("target_status")
        return values
