from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.helper import write_audit_event
from app.models.enums import LifecycleStatus, PaymentMethod
from app.models.expense import Expense, ExpenseLineItem
from app.models.source_event import SourceEvent
from app.repositories.expense import ExpenseRepository

if TYPE_CHECKING:
    pass


class ExpenseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ExpenseRepository(session)

    async def create_manual_expense(
        self,
        project_id: UUID,
        created_by: UUID,
        transaction_date: str,
        subtotal: Decimal | float,
        tax_amount: Decimal | float,
        total: Decimal | float,
        currency: str = "INR",
        payment_method: str = "CASH",
        vendor_id: UUID | None = None,
        category_id: UUID | None = None,
        line_items: list[dict] | None = None,
        vendor_name: str | None = None,
        gstin_supplier: str | None = None,
        hsn_sac_code: str | None = None,
        cgst_amount: Decimal | float | None = None,
        sgst_amount: Decimal | float | None = None,
        igst_amount: Decimal | float | None = None,
        irn: str | None = None,
    ) -> "Expense":
        from datetime import date

        from app.models.expense import Expense
        from app.models.vendor import Vendor

        # Parse transaction_date
        transaction_date_obj = date.fromisoformat(transaction_date)

        # Create vendor if name provided but no vendor_id
        if vendor_name and not vendor_id:
            from sqlalchemy import select as _select

            # First try to find existing vendor by name
            existing = await self.session.execute(
                _select(Vendor).where(Vendor.name == vendor_name).limit(1)
            )
            existing_vendor = existing.scalar_one_or_none()
            if existing_vendor:
                vendor_id = existing_vendor.id
            else:
                vendor = Vendor(name=vendor_name)
                self.session.add(vendor)
                # Flush in its own isolated step before any other flush
                await self.session.flush([vendor])
                vendor_id = vendor.id


        # Create source event for manual entry
        source_event = SourceEvent(
            source="manual",
            external_id=None,  # Manual entry has no external ID
            idempotency_key=str(uuid4()),
            raw_payload={"manual": True},
        )
        self.session.add(source_event)
        await self.session.flush()

        # Write audit event for source event creation
        source_audit_event_id = await write_audit_event(
            session=self.session,
            event_type="source_event.created",
            entity_type="source_event",
            entity_id=source_event.id,
            actor_id=created_by,
            payload={"source": "manual", "idempotency_key": source_event.idempotency_key},
        )

        subtotal_dec = Decimal(str(subtotal))
        tax_amount_dec = Decimal(str(tax_amount))
        total_dec = Decimal(str(total))
        cgst_dec = Decimal(str(cgst_amount)) if cgst_amount is not None else None
        sgst_dec = Decimal(str(sgst_amount)) if sgst_amount is not None else None
        igst_dec = Decimal(str(igst_amount)) if igst_amount is not None else None

        expense = Expense(
            project_id=project_id,
            source_event_id=source_event.id,
            vendor_id=vendor_id,
            category_id=category_id,
            transaction_date=transaction_date_obj,
            subtotal=subtotal_dec,
            tax_amount=tax_amount_dec,
            total=total_dec,
            currency=currency,
            payment_method=PaymentMethod(payment_method),
            gstin_supplier=gstin_supplier,
            hsn_sac_code=hsn_sac_code,
            cgst_amount=cgst_dec,
            sgst_amount=sgst_dec,
            igst_amount=igst_dec,
            irn=irn,
            lifecycle_status=LifecycleStatus.RECEIVED,
            source_audit_event_id=source_audit_event_id,
            confidence_score=None,
            extraction_payload={},
        )

        # Add line items
        if line_items:
            for item_data in line_items:
                line_item = ExpenseLineItem(
                    description=item_data["description"],
                    quantity=item_data.get("quantity"),
                    unit_price=item_data.get("unit_price"),
                    amount=item_data["amount"],
                    tax_amount=item_data.get("tax_amount"),
                )
                expense.line_items.append(line_item)

        self.session.add(expense)
        await self.session.flush()

        # Write audit event for expense creation
        await write_audit_event(
            session=self.session,
            event_type="expense.created",
            entity_type="expense",
            entity_id=expense.id,
            actor_id=created_by,
            payload={
                "project_id": str(project_id),
                "total": float(total),
                "vendor_id": str(vendor_id) if vendor_id else None,
                "source_event_id": str(source_event.id),
            },
            causation_id=source_audit_event_id,
        )

        await self.session.refresh(expense, attribute_names=["vendor", "category", "line_items"])
        return expense

    async def get_expense(self, expense_id: UUID) -> "Expense | None":
        return await self.repo.get_by_id(expense_id)

    async def list_expenses(
        self,
        project_id: UUID | None = None,
        project_ids: list[UUID] | None = None,
        vendor_id: UUID | None = None,
        category_id: UUID | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list["Expense"]:
        return await self.repo.list(
            project_id=project_id,
            project_ids=project_ids,
            vendor_id=vendor_id,
            category_id=category_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    async def count(
        self,
        project_id: UUID | None = None,
        project_ids: list[UUID] | None = None,
        vendor_id: UUID | None = None,
        category_id: UUID | None = None,
        status: str | None = None,
    ) -> int:
        return await self.repo.count(
            project_id=project_id,
            project_ids=project_ids,
            vendor_id=vendor_id,
            category_id=category_id,
            status=status,
        )

    async def transition_status(
        self,
        expense_id: UUID,
        new_status: str,
        actor_id: UUID | None = None,
        audit_event_id: UUID | None = None,
    ) -> "Expense":
        expense = await self.repo.get_by_id(expense_id)
        if not expense:
            raise ValueError("Expense not found")
        return await self.repo.transition_status(
            expense, new_status, actor_id=actor_id, audit_event_id=audit_event_id
        )

    async def update_expense(
        self,
        expense_id: UUID,
        update_data: dict,
        actor_id: UUID | None = None,
    ) -> "Expense":
        """Update an existing expense with permitted fields."""
        expense = await self.repo.get_by_id(expense_id)
        if not expense:
            raise ValueError("Expense not found")

        permitted_fields = {
            "transaction_date",
            "subtotal",
            "tax_amount",
            "total",
            "currency",
            "vendor_id",
            "category_id",
            "gstin_supplier",
            "hsn_sac_code",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "irn",
        }

        # Construct proposed composite state and validate financial invariants
        from decimal import Decimal

        proposed_subtotal = Decimal(str(update_data.get("subtotal", expense.subtotal)))
        proposed_tax = Decimal(str(update_data.get("tax_amount", expense.tax_amount)))
        proposed_total = Decimal(str(update_data.get("total", expense.total)))

        if proposed_subtotal < Decimal("0"):
            raise ValueError("subtotal must be non-negative")
        if proposed_tax < Decimal("0"):
            raise ValueError("tax_amount must be non-negative")
        if proposed_total < Decimal("0"):
            raise ValueError("total must be non-negative")

        if proposed_subtotal + proposed_tax != proposed_total:
            raise ValueError(
                f"Financial invariant violated: subtotal ({proposed_subtotal}) + tax_amount ({proposed_tax}) "
                f"must equal total ({proposed_total})"
            )

        raw_cgst = update_data.get("cgst_amount", expense.cgst_amount)
        raw_sgst = update_data.get("sgst_amount", expense.sgst_amount)
        raw_igst = update_data.get("igst_amount", expense.igst_amount)

        proposed_cgst = Decimal(str(raw_cgst)) if raw_cgst is not None else None
        proposed_sgst = Decimal(str(raw_sgst)) if raw_sgst is not None else None
        proposed_igst = Decimal(str(raw_igst)) if raw_igst is not None else None

        if proposed_cgst is not None and proposed_cgst < Decimal("0"):
            raise ValueError("cgst_amount must be non-negative")
        if proposed_sgst is not None and proposed_sgst < Decimal("0"):
            raise ValueError("sgst_amount must be non-negative")
        if proposed_igst is not None and proposed_igst < Decimal("0"):
            raise ValueError("igst_amount must be non-negative")

        if proposed_tax > Decimal("0") and (proposed_cgst or proposed_sgst or proposed_igst):
            if proposed_igst and proposed_igst > Decimal("0"):
                if proposed_igst != proposed_tax:
                    raise ValueError(f"igst_amount ({proposed_igst}) must equal tax_amount ({proposed_tax})")
            elif (proposed_cgst and proposed_cgst > Decimal("0")) or (proposed_sgst and proposed_sgst > Decimal("0")):
                c = proposed_cgst or Decimal("0")
                s = proposed_sgst or Decimal("0")
                if c + s != proposed_tax:
                    raise ValueError(f"cgst_amount ({c}) + sgst_amount ({s}) must equal tax_amount ({proposed_tax})")

        updated_fields = {}
        for key, value in update_data.items():
            if key in permitted_fields and value is not None:
                setattr(expense, key, value)
                updated_fields[key] = str(value)
            elif key == "payment_method" and value is not None:
                expense.payment_method = PaymentMethod(value)
                updated_fields[key] = str(value)
            elif key == "lifecycle_status" and value is not None:
                expense.lifecycle_status = LifecycleStatus(value)
                updated_fields[key] = str(value)

        await self.session.flush()

        if updated_fields and actor_id:
            await write_audit_event(
                session=self.session,
                event_type="expense.updated",
                entity_type="expense",
                entity_id=expense.id,
                actor_id=actor_id,
                payload=updated_fields,
            )

        await self.session.commit()
        await self.session.refresh(expense, attribute_names=["vendor", "category", "line_items"])
        return expense
