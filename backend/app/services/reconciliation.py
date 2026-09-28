"""Reconciliation service for expense-payment matching."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.helper import write_audit_event
from app.core.logging import get_logger
from app.models.enums import LifecycleStatus, MatchBasis, ReconciliationStatus
from app.models.expense import Expense
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_record import ReconciliationRecord

logger = get_logger(__name__)


class ReconciliationService:
    """Service for matching expenses to payment events."""

    # Matching thresholds
    EXACT_AMOUNT_TOLERANCE = Decimal("0.01")
    DATE_WINDOW_DAYS = 3
    CONFIDENCE_THRESHOLD = Decimal("0.8")
    AMBIGUOUS_THRESHOLD = Decimal("0.6")

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def session(self) -> AsyncSession:
        """Alias for db session for test compatibility."""
        return self.db

    async def find_candidates(
        self,
        expense: Expense,
        project_id: UUID | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find potential payment event matches for an expense."""
        # If project_id is specified and expense belongs to a different project, return empty
        if project_id and expense.project_id and expense.project_id != project_id:
            return []

        # Amount tolerance window (exact, 0.01 tolerance, or fuzzy within 2%)
        tolerance = (
            max(self.EXACT_AMOUNT_TOLERANCE, expense.total * Decimal("0.02"))
            if expense.total and expense.total > 0
            else Decimal("0.01")
        )
        min_amount = max(Decimal("0.00"), (expense.total or Decimal("0.00")) - tolerance)
        max_amount = (expense.total or Decimal("0.00")) + tolerance

        conditions = [PaymentEvent.amount.between(min_amount, max_amount)]

        # Also match if UPI or bank reference is present in extraction payload
        if expense.extraction_payload:
            upi_ref = expense.extraction_payload.get("upi_reference")
            if upi_ref:
                conditions.append(PaymentEvent.upi_reference == str(upi_ref).strip())
            bank_ref = expense.extraction_payload.get("bank_reference")
            if bank_ref:
                conditions.append(PaymentEvent.bank_reference == str(bank_ref).strip())

        query = select(PaymentEvent).where(or_(*conditions))

        # Date window filter
        if expense.transaction_date:
            date_from_obj = expense.transaction_date - timedelta(days=self.DATE_WINDOW_DAYS)
            date_to_obj = expense.transaction_date + timedelta(days=self.DATE_WINDOW_DAYS)
            start_dt = datetime.combine(date_from_obj, datetime.min.time(), tzinfo=UTC)
            end_dt = datetime.combine(date_to_obj, datetime.max.time(), tzinfo=UTC)
            query = query.where(
                PaymentEvent.occurred_at >= start_dt,
                PaymentEvent.occurred_at <= end_dt,
            )

        if date_from:
            query = query.where(PaymentEvent.occurred_at >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.where(PaymentEvent.occurred_at <= datetime.fromisoformat(date_to))

        # Exclude already matched payments
        subquery = select(ReconciliationRecord.payment_event_id).where(
            ReconciliationRecord.payment_event_id.is_not(None)
        )
        query = query.where(PaymentEvent.id.not_in(subquery))

        result = await self.db.execute(query)
        payments = result.scalars().all()

        # Eagerly resolve vendor name to avoid MissingGreenlet error in asyncpg
        vendor_name = None
        if expense.vendor_id:
            try:
                from app.models.vendor import Vendor
                vendor = await self.db.get(Vendor, expense.vendor_id)
                if vendor:
                    vendor_name = vendor.name
            except Exception:
                pass
        if not vendor_name and expense.extraction_payload:
            vendor_name = expense.extraction_payload.get("vendor_name")

        candidates = []
        for payment in payments:
            score, basis = self._calculate_match_score(expense, payment, vendor_name=vendor_name)
            if score > Decimal("0.0"):
                candidates.append({
                    "payment_event_id": payment.id,
                    "amount": float(payment.amount),
                    "occurred_at": payment.occurred_at.isoformat(),
                    "payee_raw_text": payment.payee_raw_text,
                    "upi_reference": payment.upi_reference,
                    "bank_reference": payment.bank_reference,
                    "payment_method": payment.payment_method.value,
                    "match_score": float(score),
                    "match_basis": basis.value,
                })

        # Sort by score descending
        candidates.sort(key=lambda x: float(x["match_score"]), reverse=True)  # type: ignore[arg-type]
        return candidates

    def _calculate_match_score(
        self,
        expense: Expense,
        payment: PaymentEvent,
        vendor_name: str | None = None,
    ) -> tuple[Decimal, MatchBasis]:
        """Calculate match score between expense and payment event."""
        # 1. Exact reference match (UPI / bank reference)
        ref_match = False
        if expense.payment_method and payment.payment_method:
            if expense.payment_method.value == payment.payment_method.value:
                if expense.extraction_payload:
                    upi_ref = expense.extraction_payload.get("upi_reference")
                    if (
                        upi_ref
                        and payment.upi_reference
                        and str(upi_ref).strip().lower() == payment.upi_reference.strip().lower()
                    ):
                        ref_match = True
                    bank_ref = expense.extraction_payload.get("bank_reference")
                    if (
                        bank_ref
                        and payment.bank_reference
                        and str(bank_ref).strip().lower() == payment.bank_reference.strip().lower()
                    ):
                        ref_match = True

        if ref_match:
            amount_diff = abs(expense.total - payment.amount)
            if amount_diff <= self.EXACT_AMOUNT_TOLERANCE:
                return Decimal("1.0"), MatchBasis.REFERENCE
            elif expense.total > 0 and (amount_diff / expense.total) <= Decimal("0.02"):
                return Decimal("0.90"), MatchBasis.REFERENCE

        # 2. Scored match components: Amount, Date, Payee
        amount_diff = abs(expense.total - payment.amount)
        if amount_diff == Decimal("0"):
            amount_score = 1.0
        elif amount_diff <= self.EXACT_AMOUNT_TOLERANCE:
            amount_score = 0.95
        elif expense.total > 0 and (amount_diff / expense.total) <= Decimal("0.01"):
            amount_score = 0.80
        elif expense.total > 0 and (amount_diff / expense.total) <= Decimal("0.02"):
            amount_score = 0.60
        else:
            amount_score = 0.0

        if amount_score == 0.0:
            return Decimal("0.0"), MatchBasis.SCORED

        # Date proximity score
        date_score = 0.3
        if expense.transaction_date and payment.occurred_at:
            payment_date = (
                payment.occurred_at.date()
                if hasattr(payment.occurred_at, "date")
                else payment.occurred_at
            )
            date_diff = abs((expense.transaction_date - payment_date).days)
            if date_diff == 0:
                date_score = 1.0
            elif date_diff == 1:
                date_score = 0.85
            elif date_diff == 2:
                date_score = 0.70
            elif date_diff <= self.DATE_WINDOW_DAYS:
                date_score = 0.50
            elif date_diff <= 7:
                date_score = 0.20
            else:
                date_score = 0.0

        # Payee similarity score
        if vendor_name is None:
            try:
                vendor_name = expense.vendor.name if expense.vendor else None
            except Exception:
                vendor_name = None
        if vendor_name is None and expense.extraction_payload:
            vendor_name = expense.extraction_payload.get("vendor_name")

        has_payee_info = bool(vendor_name and payment.payee_raw_text)
        if has_payee_info:
            similarity = self._fuzzy_match(str(vendor_name), payment.payee_raw_text)
            if similarity >= 0.8:
                payee_score = 1.0
            elif similarity >= 0.5:
                payee_score = 0.7
            elif similarity >= 0.3:
                payee_score = 0.4
            else:
                payee_score = 0.0
        else:
            payee_score = 0.0

        # Composite score calculation (Weights: Amount: 0.45, Date: 0.20, Payee: 0.35)
        composite = (amount_score * 0.45) + (date_score * 0.20) + (payee_score * 0.35)

        # Financial integrity rule: Do not assign high confidence (>= 0.80) based only on amount/date
        # when payee similarity is absent or poor. Cap at 0.65 to ensure it is marked AMBIGUOUS
        # and requires human review instead of auto-matching.
        if (not has_payee_info or payee_score < 0.5) and composite > 0.65:
            composite = 0.65

        score = Decimal(str(round(composite, 2)))
        return score, MatchBasis.SCORED

    def _fuzzy_match(self, s1: str, s2: str) -> float:
        """Fuzzy string matching using token overlap and sequence ratio."""
        if not s1 or not s2:
            return 0.0

        s1_clean = s1.lower().strip()
        s2_clean = s2.lower().strip()
        if s1_clean == s2_clean:
            return 1.0

        tokens1 = set(s1_clean.split())
        tokens2 = set(s2_clean.split())
        if not tokens1 or not tokens2:
            return 0.0

        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)

        from difflib import SequenceMatcher
        seq_ratio = SequenceMatcher(None, s1_clean, s2_clean).ratio()

        return max(jaccard, seq_ratio)

    async def reconcile_expense(
        self,
        expense_id: UUID,
        payment_event_id: UUID | None = None,
        auto_match: bool = True,
    ) -> ReconciliationRecord:
        """
        Reconcile an expense with a payment event.

        If payment_event_id is provided, manually match to that payment.
        If auto_match is True, find the best candidate automatically.
        """
        expense = await self.db.get(Expense, expense_id)
        if not expense:
            raise ValueError(f"Expense {expense_id} not found")

        # Check if already reconciled
        existing = await self.db.execute(
            select(ReconciliationRecord).where(
                ReconciliationRecord.expense_id == expense_id,
                ReconciliationRecord.payment_event_id.is_not(None),
            )
        )
        existing_record = existing.scalars().first()
        if existing_record:
            return existing_record

        payment_event = None
        match_basis = MatchBasis.MANUAL
        match_score = Decimal("1.0")

        if payment_event_id:
            # Manual match
            payment_event = await self.db.get(PaymentEvent, payment_event_id)
            if not payment_event:
                raise ValueError(f"Payment event {payment_event_id} not found")
        elif auto_match:
            # Auto-match
            candidates = await self.find_candidates(expense)
            if candidates:
                best = candidates[0]
                if best["match_score"] >= float(self.CONFIDENCE_THRESHOLD):
                    payment_event = await self.db.get(PaymentEvent, best["payment_event_id"])
                    match_basis = MatchBasis(best["match_basis"])
                    match_score = Decimal(str(best["match_score"]))
                elif best["match_score"] >= float(self.AMBIGUOUS_THRESHOLD):
                    payment_event = await self.db.get(PaymentEvent, best["payment_event_id"])
                    match_basis = MatchBasis(best["match_basis"])
                    match_score = Decimal(str(best["match_score"]))
                else:
                    # No good match - create unmatched record
                    return await self.create_reconciliation(
                        expense_id=expense_id,
                        payment_event_id=None,
                        match_basis=MatchBasis.SCORED,
                        match_score=Decimal("0.0"),
                    )
            else:
                # No candidates - create unmatched record
                return await self.create_reconciliation(
                    expense_id=expense_id,
                    payment_event_id=None,
                    match_basis=MatchBasis.SCORED,
                    match_score=Decimal("0.0"),
                )
        else:
            raise ValueError("Either payment_event_id or auto_match=True must be provided")

        if not payment_event:
            # Create unmatched record
            return await self.create_reconciliation(
                expense_id=expense_id,
                payment_event_id=None,
                match_basis=MatchBasis.SCORED,
                match_score=Decimal("0.0"),
            )

        # Create reconciliation record
        return await self.create_reconciliation(
            expense_id=expense_id,
            payment_event_id=payment_event.id,
            match_basis=match_basis,
            match_score=match_score,
        )

    async def create_reconciliation(
        self,
        expense_id: UUID,
        payment_event_id: UUID | None,
        match_basis: MatchBasis,
        match_score: Decimal,
        resolved_by: UUID | None = None,
        resolution_reason: str | None = None,
    ) -> ReconciliationRecord:
        """Create a reconciliation record."""
        expense = await self.db.get(Expense, expense_id)
        if not expense:
            raise ValueError(f"Expense {expense_id} not found")

        # Determine status based on match score
        if match_score >= self.CONFIDENCE_THRESHOLD:
            status = ReconciliationStatus.MATCHED
        elif match_score >= self.AMBIGUOUS_THRESHOLD:
            status = ReconciliationStatus.AMBIGUOUS
        else:
            status = ReconciliationStatus.UNMATCHED

        record = ReconciliationRecord(
            expense_id=expense_id,
            payment_event_id=payment_event_id,
            status=status,
            match_basis=match_basis,
            match_score=match_score,
            resolved_by=resolved_by,
            resolution_reason=resolution_reason,
        )

        self.db.add(record)

        # Update expense status if matched
        if status == ReconciliationStatus.MATCHED:
            expense.lifecycle_status = LifecycleStatus.RECONCILED

        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="expense.reconciled",
            entity_type="reconciliation",
            entity_id=record.id,
            actor_id=resolved_by,
            payload={
                "expense_id": str(expense_id),
                "payment_event_id": str(payment_event_id) if payment_event_id else None,
                "status": status.value,
                "match_basis": match_basis.value,
                "match_score": float(match_score),
            },
        )

        return record

    async def confirm_reconciliation(
        self,
        reconciliation_id: UUID,
        reviewer_id: UUID,
        notes: str | None = None,
        match_basis: MatchBasis | None = None,
    ) -> ReconciliationRecord:
        """Confirm a reconciliation (manual review)."""
        record = await self.db.get(ReconciliationRecord, reconciliation_id)
        if not record:
            raise ValueError(f"Reconciliation {reconciliation_id} not found")

        record.status = ReconciliationStatus.MATCHED
        record.match_basis = match_basis or MatchBasis.MANUAL
        record.resolved_by = reviewer_id
        record.resolution_reason = notes
        record.updated_at = datetime.now(UTC)

        # Update expense to RECONCILED
        expense = await self.db.get(Expense, record.expense_id)
        if expense:
            expense.lifecycle_status = LifecycleStatus.RECONCILED

        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="reconciliation.confirmed",
            entity_type="reconciliation",
            entity_id=record.id,
            actor_id=reviewer_id,
            payload={"notes": notes},
        )

        return record

    async def reject_reconciliation(
        self,
        reviewer_id: UUID,
        reconciliation_id: UUID | None = None,
        expense_id: UUID | None = None,
        notes: str | None = None,
    ) -> ReconciliationRecord:
        """Reject a reconciliation by reconciliation_id or expense_id."""
        if reconciliation_id:
            record = await self.db.get(ReconciliationRecord, reconciliation_id)
        elif expense_id:
            result = await self.db.execute(
                select(ReconciliationRecord).where(
                    ReconciliationRecord.expense_id == expense_id,
                    ReconciliationRecord.payment_event_id.is_not(None),
                ).order_by(ReconciliationRecord.created_at.desc())
            )
            record = result.scalars().first()
        else:
            raise ValueError("Either reconciliation_id or expense_id must be provided")

        if not record:
            raise ValueError("Reconciliation not found")

        record.status = ReconciliationStatus.UNMATCHED
        record.resolved_by = reviewer_id
        record.resolution_reason = notes
        record.updated_at = datetime.now(UTC)

        # Reset expense to RECONCILED
        expense = await self.db.get(Expense, record.expense_id)
        if expense:
            expense.lifecycle_status = LifecycleStatus.RECONCILED

        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="reconciliation.rejected",
            entity_type="reconciliation",
            entity_id=record.id,
            actor_id=reviewer_id,
            payload={"notes": notes},
        )

        return record

    async def unmatch_reconciliation(
        self,
        reviewer_id: UUID,
        reconciliation_id: UUID | None = None,
        expense_id: UUID | None = None,
        notes: str | None = None,
    ) -> ReconciliationRecord:
        """Unmatch a previously matched reconciliation by reconciliation_id or expense_id."""
        if reconciliation_id:
            record = await self.db.get(ReconciliationRecord, reconciliation_id)
        elif expense_id:
            result = await self.db.execute(
                select(ReconciliationRecord).where(
                    ReconciliationRecord.expense_id == expense_id,
                    ReconciliationRecord.payment_event_id.is_not(None),
                ).order_by(ReconciliationRecord.created_at.desc())
            )
            record = result.scalars().first()
        else:
            raise ValueError("Either reconciliation_id or expense_id must be provided")

        if not record:
            raise ValueError("Reconciliation not found")

        if record.status != ReconciliationStatus.MATCHED:
            raise ValueError("Only matched reconciliations can be unmatched")

        record.status = ReconciliationStatus.UNMATCHED
        record.payment_event_id = None
        record.resolved_by = reviewer_id
        record.resolution_reason = notes
        record.updated_at = datetime.now(UTC)

        # Reset expense to STAGED
        expense = await self.db.get(Expense, record.expense_id)
        if expense:
            expense.lifecycle_status = LifecycleStatus.STAGED

        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="reconciliation.unmatched",
            entity_type="reconciliation",
            entity_id=record.id,
            actor_id=reviewer_id,
            payload={"notes": notes},
        )

        return record

    async def list_reconciliations(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        project_id: UUID | None = None,
    ) -> dict[str, Any]:
        """List reconciliations with pagination."""
        base_query = select(ReconciliationRecord)

        if project_id:
            base_query = base_query.where(
                ReconciliationRecord.expense_id.in_(
                    select(Expense.id).where(Expense.project_id == project_id)
                )
            )

        if status_filter:
            base_query = base_query.where(ReconciliationRecord.status == ReconciliationStatus(status_filter))

        # Total count
        total_q = select(func.count(ReconciliationRecord.id))
        if project_id:
            total_q = total_q.where(
                ReconciliationRecord.expense_id.in_(
                    select(Expense.id).where(Expense.project_id == project_id)
                )
            )

        total_result = await self.db.execute(total_q)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = base_query.offset(offset).limit(page_size).order_by(ReconciliationRecord.created_at.desc())

        result = await self.db.execute(query)
        records = result.scalars().all()

        # Build detailed response
        items = []
        for record in records:
            expense = await self.db.get(Expense, record.expense_id)
            payment = await self.db.get(PaymentEvent, record.payment_event_id) if record.payment_event_id else None

            items.append({
                "id": record.id,
                "expense_id": record.expense_id,
                "expense_vendor": expense.vendor.name if expense and expense.vendor else None,
                "expense_amount": float(expense.total) if expense else 0,
                "expense_date": expense.transaction_date.isoformat() if expense and expense.transaction_date else None,
                "payment_event_id": record.payment_event_id,
                "payment_amount": float(payment.amount) if payment else None,
                "payment_date": payment.occurred_at.isoformat() if payment else None,
                "payment_payee": payment.payee_raw_text if payment else None,
                "payment_upi_ref": payment.upi_reference if payment else None,
                "payment_bank_ref": payment.bank_reference if payment else None,
                "status": record.status.value,
                "match_basis": record.match_basis.value if record.match_basis else None,
                "match_score": float(record.match_score) if record.match_score else None,
                "resolved_by": record.resolved_by,
                "resolution_reason": record.resolution_reason,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_reconciliation_stats(self, project_id: UUID | None = None) -> dict[str, int]:
        """Get reconciliation statistics."""
        # Use completely independent queries to avoid any query building issues
        if project_id:
            total = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    ReconciliationRecord.expense_id.in_(
                        select(Expense.id).where(Expense.project_id == project_id)
                    )
                )
            )
            matched = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    ReconciliationRecord.expense_id.in_(
                        select(Expense.id).where(Expense.project_id == project_id)
                    ),
                    cast(ReconciliationRecord.status, String) == ReconciliationStatus.MATCHED.value,
                )
            )
            unmatched = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    ReconciliationRecord.expense_id.in_(
                        select(Expense.id).where(Expense.project_id == project_id)
                    ),
                    cast(ReconciliationRecord.status, String) == ReconciliationStatus.UNMATCHED.value,
                )
            )
            ambiguous = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    ReconciliationRecord.expense_id.in_(
                        select(Expense.id).where(Expense.project_id == project_id)
                    ),
                    cast(ReconciliationRecord.status, String) == ReconciliationStatus.AMBIGUOUS.value,
                )
            )
            manually_resolved = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    ReconciliationRecord.expense_id.in_(
                        select(Expense.id).where(Expense.project_id == project_id)
                    ),
                    cast(ReconciliationRecord.match_basis, String) == MatchBasis.MANUAL.value,
                )
            )
        else:
            total = await self.db.scalar(select(func.count(ReconciliationRecord.id)))
            matched = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    cast(ReconciliationRecord.status, String) == ReconciliationStatus.MATCHED.value,
                )
            )
            unmatched = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    cast(ReconciliationRecord.status, String) == ReconciliationStatus.UNMATCHED.value,
                )
            )
            ambiguous = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    cast(ReconciliationRecord.status, String) == ReconciliationStatus.AMBIGUOUS.value,
                )
            )
            manually_resolved = await self.db.scalar(
                select(func.count(ReconciliationRecord.id)).where(
                    cast(ReconciliationRecord.match_basis, String) == MatchBasis.MANUAL.value,
                )
            )

        # Pending auto-match: RECONCILED expenses without reconciliation record
        reconciled_query = select(func.count(Expense.id)).where(
            cast(Expense.lifecycle_status, String) == LifecycleStatus.RECONCILED.value
        )
        if project_id:
            reconciled_query = reconciled_query.where(Expense.project_id == project_id)

        reconciled_count = await self.db.scalar(reconciled_query)

        # Subtract already reconciled
        pending = (reconciled_count or 0) - (total or 0)

        return {
            "total": total or 0,
            "matched": matched or 0,
            "unmatched": unmatched or 0,
            "ambiguous": ambiguous or 0,
            "manually_resolved": manually_resolved or 0,
            "pending_auto_match": max(0, pending),
        }

    async def auto_match_batch(
        self,
        project_id: UUID | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        confidence_threshold: Decimal = Decimal("0.8"),
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run auto-matching for multiple expenses."""
        # Get STAGED and RECONCILED expenses without reconciliation
        query = select(Expense).where(
            cast(Expense.lifecycle_status, String).in_([
                LifecycleStatus.STAGED.value,
                LifecycleStatus.RECONCILED.value,
            ])
        )

        if project_id:
            query = query.where(Expense.project_id == project_id)

        # Exclude already reconciled
        query = query.where(
            ~Expense.id.in_(
                select(ReconciliationRecord.expense_id).where(
                    ReconciliationRecord.payment_event_id.is_not(None)
                )
            )
        )

        if date_from:
            query = query.where(Expense.transaction_date >= datetime.fromisoformat(date_from).date())
        if date_to:
            query = query.where(Expense.transaction_date <= datetime.fromisoformat(date_to).date())

        result = await self.db.execute(query)
        expenses = result.scalars().all()

        processed = 0
        matched = 0
        ambiguous = 0
        unmatched = 0
        errors = 0
        matches = []

        for expense in expenses:
            try:
                candidates = await self.find_candidates(expense)
                processed += 1

                if candidates:
                    best = candidates[0]
                    if best["match_score"] >= float(confidence_threshold):
                        if not dry_run:
                            await self.create_reconciliation(
                                expense_id=expense.id,
                                payment_event_id=best["payment_event_id"],
                                match_basis=MatchBasis(best["match_basis"]),
                                match_score=Decimal(str(best["match_score"])),
                            )
                        matched += 1
                        matches.append({
                            "expense_id": str(expense.id),
                            "payment_event_id": best["payment_event_id"],
                            "match_score": best["match_score"],
                            "match_basis": best["match_basis"],
                        })
                    elif best["match_score"] >= 0.5:
                        ambiguous += 1
                    else:
                        unmatched += 1
                else:
                    unmatched += 1

            except Exception as e:
                logger.error("Auto-match error", expense_id=str(expense.id), error=str(e))
                errors += 1

        if not dry_run:
            await self.db.commit()

        return {
            "processed": processed,
            "matched": matched,
            "ambiguous": ambiguous,
            "unmatched": unmatched,
            "errors": errors,
            "matches": matches,
        }


def create_reconciliation_service(db: AsyncSession) -> ReconciliationService:
    """Factory for creating ReconciliationService."""
    return ReconciliationService(db)
