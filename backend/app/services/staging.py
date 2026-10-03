"""Staging service for human review workflow."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.helper import write_audit_event
from app.core.logging import get_logger
from app.models.enums import JobStatus, JobType, LifecycleStatus
from app.models.evidence import Evidence
from app.models.expense import Expense
from app.models.processing_job import ProcessingJob

logger = get_logger(__name__)


class StagingService:
    """Service for managing staged expenses awaiting human review."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def stage_expenses(
        self,
        expense_ids: list[UUID],
        reviewer_id: UUID | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """
        Stage expenses for human review.

        Transitions expenses from EXTRACTED to STAGED status.
        """
        staged = []
        errors = []

        for expense_id in expense_ids:
            expense = await self.db.get(Expense, expense_id, options=[selectinload(Expense.vendor)])
            if not expense:
                errors.append(f"Expense {expense_id} not found")
                continue

            if expense.lifecycle_status not in [
                LifecycleStatus.EXTRACTED,
                LifecycleStatus.NEEDS_CONFIRMATION,
            ]:
                errors.append(
                    f"Expense {expense_id} cannot be staged (status: {expense.lifecycle_status})"
                )
                continue

            # Get extraction result from LLM_EXTRACT job
            extraction_result = await self._get_extraction_result(expense_id)
            validation_errors = extraction_result.get("validation_errors", [])
            validation_warnings = extraction_result.get("validation_warnings", [])

            # Get evidence
            evidence_result = await self.db.execute(
                select(Evidence).where(Evidence.expense_id == expense_id)
            )
            evidence_ids = [e.id for e in evidence_result.scalars().all()]

            # Build staged item
            staged_item = {
                "expense_id": expense.id,
                "project_id": expense.project_id,
                "source_event_id": expense.source_event_id,
                "evidence_ids": evidence_ids,
                "vendor_name": expense.vendor.name if expense.vendor else extraction_result.get("vendor_name"),
                "vendor_gstin": expense.gstin_supplier or extraction_result.get("vendor_gstin"),
                "transaction_date": expense.transaction_date.isoformat() if expense.transaction_date else extraction_result.get("transaction_date"),
                "invoice_number": extraction_result.get("invoice_number"),
                "subtotal": float(expense.subtotal) if expense.subtotal else extraction_result.get("subtotal"),
                "tax_amount": float(expense.tax_amount) if expense.tax_amount else extraction_result.get("tax_amount"),
                "total_amount": float(expense.total) if expense.total else extraction_result.get("total_amount"),
                "currency": expense.currency,
                "payment_method": expense.payment_method.value if expense.payment_method else extraction_result.get("payment_method"),
                "cgst_amount": float(expense.cgst_amount) if expense.cgst_amount else extraction_result.get("cgst_amount"),
                "sgst_amount": float(expense.sgst_amount) if expense.sgst_amount else extraction_result.get("sgst_amount"),
                "igst_amount": float(expense.igst_amount) if expense.igst_amount else extraction_result.get("igst_amount"),
                "hsn_sac_code": expense.hsn_sac_code or extraction_result.get("hsn_sac_code"),
                "irn": expense.irn or extraction_result.get("irn"),
                "confidence_score": extraction_result.get("confidence_score", 0.0),
                "extraction_result": extraction_result,
                "validation_errors": validation_errors,
                "validation_warnings": validation_warnings,
                "line_items": extraction_result.get("line_items", []),
                "staged_at": datetime.now(UTC),
                "staged_by": reviewer_id,
            }

            staged.append(staged_item)

            # Update expense status
            expense.lifecycle_status = LifecycleStatus.STAGED
            await self.db.flush()

            # Audit trail
            await write_audit_event(
                session=self.db,
                event_type="expense.staged",
                entity_type="expense",
                entity_id=expense.id,
                actor_id=reviewer_id,
                payload={
                    "notes": notes,
                    "confidence_score": extraction_result.get("confidence_score"),
                    "validation_errors": validation_errors,
                },
            )

        await self.db.commit()

        return {
            "staged_count": len(staged),
            "errors": errors,
            "staged_expenses": staged,
        }

    async def _get_extraction_result(self, expense_id: UUID) -> dict[str, Any]:
        """Get latest LLM extraction result for expense."""
        from sqlalchemy import select

        result = await self.db.execute(
            select(ProcessingJob).where(
                ProcessingJob.source_event_id == expense_id,
                ProcessingJob.job_type == JobType.LLM_EXTRACT,
                ProcessingJob.status == JobStatus.SUCCEEDED,
            ).order_by(ProcessingJob.created_at.desc())
        )
        job = result.scalars().first()
        return job.result if job and job.result else {}

    async def get_staged_expense(self, expense_id: UUID) -> dict[str, Any] | None:
        """Get detailed staged expense for review."""
        expense = await self.db.get(Expense, expense_id, options=[selectinload(Expense.vendor)])
        if not expense or expense.lifecycle_status != LifecycleStatus.STAGED:
            return None

        extraction_result = await self._get_extraction_result(expense_id)

        evidence_result = await self.db.execute(
            select(Evidence).where(Evidence.expense_id == expense_id)
        )
        evidence_ids = [e.id for e in evidence_result.scalars().all()]

        return {
            "expense_id": expense.id,
            "project_id": expense.project_id,
            "project_name": expense.project.name if expense.project else None,
            "source_event_id": expense.source_event_id,
            "evidence_ids": evidence_ids,
            "vendor_name": expense.vendor.name if expense.vendor else extraction_result.get("vendor_name"),
            "vendor_gstin": expense.gstin_supplier or extraction_result.get("vendor_gstin"),
            "transaction_date": expense.transaction_date.isoformat() if expense.transaction_date else extraction_result.get("transaction_date"),
            "invoice_number": extraction_result.get("invoice_number"),
            "subtotal": float(expense.subtotal) if expense.subtotal else extraction_result.get("subtotal"),
            "tax_amount": float(expense.tax_amount) if expense.tax_amount else extraction_result.get("tax_amount"),
            "total_amount": float(expense.total) if expense.total else extraction_result.get("total_amount"),
            "currency": expense.currency,
            "payment_method": expense.payment_method.value if expense.payment_method else extraction_result.get("payment_method"),
            "cgst_amount": float(expense.cgst_amount) if expense.cgst_amount else extraction_result.get("cgst_amount"),
            "sgst_amount": float(expense.sgst_amount) if expense.sgst_amount else extraction_result.get("sgst_amount"),
            "igst_amount": float(expense.igst_amount) if expense.igst_amount else extraction_result.get("igst_amount"),
            "hsn_sac_code": expense.hsn_sac_code or extraction_result.get("hsn_sac_code"),
            "irn": expense.irn or extraction_result.get("irn"),
            "confidence_score": extraction_result.get("confidence_score", 0.0),
            "extraction_result": extraction_result,
            "validation_errors": extraction_result.get("validation_errors", []),
            "validation_warnings": extraction_result.get("validation_warnings", []),
            "line_items": extraction_result.get("line_items", []),
            "staged_at": expense.updated_at,
            "staged_by": None,  # Would need to track in audit
            "reviewer_id": None,
            "reviewed_at": None,
            "review_notes": None,
        }

    async def list_staged_expenses(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        project_ids: list[UUID] | None = None,
        project_id: UUID | None = None,
    ) -> dict[str, Any]:
        """List staged expenses with pagination and project scoping."""
        from sqlalchemy import func, select

        if project_ids is not None and len(project_ids) == 0:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        query = select(Expense).where(Expense.lifecycle_status == LifecycleStatus.STAGED).options(
            selectinload(Expense.vendor), selectinload(Expense.project)
        )

        if project_id:
            query = query.where(Expense.project_id == project_id)
        elif project_ids is not None:
            query = query.where(Expense.project_id.in_(project_ids))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Expense.updated_at.desc())

        result = await self.db.execute(query)
        expenses = result.scalars().all()

        items = []
        for expense in expenses:
            extraction_result = await self._get_extraction_result(expense.id)
            evidence_result = await self.db.execute(
                select(Evidence).where(Evidence.expense_id == expense.id)
            )
            evidence_ids = [e.id for e in evidence_result.scalars().all()]

            items.append({
                "expense_id": expense.id,
                "project_id": expense.project_id,
                "project_name": expense.project.name if expense.project else None,
                "source_event_id": expense.source_event_id,
                "evidence_ids": evidence_ids,
                "vendor_name": expense.vendor.name if expense.vendor else extraction_result.get("vendor_name"),
                "vendor_gstin": expense.gstin_supplier or extraction_result.get("vendor_gstin"),
                "transaction_date": expense.transaction_date.isoformat() if expense.transaction_date else extraction_result.get("transaction_date"),
                "invoice_number": extraction_result.get("invoice_number"),
                "subtotal": float(expense.subtotal) if expense.subtotal else extraction_result.get("subtotal"),
                "tax_amount": float(expense.tax_amount) if expense.tax_amount else extraction_result.get("tax_amount"),
                "total_amount": float(expense.total) if expense.total else extraction_result.get("total_amount"),
                "currency": expense.currency,
                "payment_method": expense.payment_method.value if expense.payment_method else extraction_result.get("payment_method"),
                "cgst_amount": float(expense.cgst_amount) if expense.cgst_amount else extraction_result.get("cgst_amount"),
                "sgst_amount": float(expense.sgst_amount) if expense.sgst_amount else extraction_result.get("sgst_amount"),
                "igst_amount": float(expense.igst_amount) if expense.igst_amount else extraction_result.get("igst_amount"),
                "hsn_sac_code": expense.hsn_sac_code or extraction_result.get("hsn_sac_code"),
                "irn": expense.irn or extraction_result.get("irn"),
                "confidence_score": extraction_result.get("confidence_score", 0.0),
                "extraction_result": extraction_result,
                "validation_errors": extraction_result.get("validation_errors", []),
                "validation_warnings": extraction_result.get("validation_warnings", []),
                "line_items": extraction_result.get("line_items", []),
                "staged_at": expense.updated_at,
                "staged_by": None,
                "reviewer_id": None,
                "reviewed_at": None,
                "review_notes": None,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def approve_expense(
        self,
        expense_id: UUID,
        reviewer_id: UUID,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Approve a staged expense."""
        expense = await self.db.get(Expense, expense_id)
        if not expense:
            raise ValueError(f"Expense {expense_id} not found")

        if expense.lifecycle_status != LifecycleStatus.STAGED:
            raise ValueError(f"Expense {expense_id} is not staged (status: {expense.lifecycle_status})")

        expense.lifecycle_status = LifecycleStatus.RECONCILED
        expense.updated_at = datetime.now(UTC)
        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="expense.approved",
            entity_type="expense",
            entity_id=expense.id,
            actor_id=reviewer_id,
            payload={"notes": notes},
        )

        await self.db.commit()

        return {
            "expense_id": expense.id,
            "action": "approve",
            "new_status": expense.lifecycle_status.value,
            "message": "Expense approved and moved to reconciliation",
        }

    async def reject_expense(
        self,
        expense_id: UUID,
        reviewer_id: UUID,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Reject a staged expense."""
        expense = await self.db.get(Expense, expense_id)
        if not expense:
            raise ValueError(f"Expense {expense_id} not found")

        if expense.lifecycle_status != LifecycleStatus.STAGED:
            raise ValueError(f"Expense {expense_id} is not staged (status: {expense.lifecycle_status})")

        expense.lifecycle_status = LifecycleStatus.REJECTED
        expense.updated_at = datetime.now(UTC)
        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="expense.rejected",
            entity_type="expense",
            entity_id=expense.id,
            actor_id=reviewer_id,
            payload={"notes": notes, "reason": "rejected_during_review"},
        )

        await self.db.commit()

        return {
            "expense_id": expense.id,
            "action": "reject",
            "new_status": expense.lifecycle_status.value,
            "message": "Expense rejected",
        }

    async def request_changes(
        self,
        expense_id: UUID,
        reviewer_id: UUID,
        notes: str | None = None,
        corrections: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Request changes to a staged expense."""
        expense = await self.db.get(Expense, expense_id)
        if not expense:
            raise ValueError(f"Expense {expense_id} not found")

        if expense.lifecycle_status != LifecycleStatus.STAGED:
            raise ValueError(f"Expense {expense_id} is not staged (status: {expense.lifecycle_status})")

        expense.lifecycle_status = LifecycleStatus.NEEDS_CONFIRMATION
        expense.updated_at = datetime.now(UTC)
        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="expense.changes_requested",
            entity_type="expense",
            entity_id=expense.id,
            actor_id=reviewer_id,
            payload={"notes": notes, "corrections": corrections},
        )

        await self.db.commit()

        return {
            "expense_id": expense.id,
            "action": "request_changes",
            "new_status": expense.lifecycle_status.value,
            "message": "Changes requested, expense returned for re-extraction",
        }

    async def get_staging_stats(
        self,
        project_ids: list[UUID] | None = None,
        project_id: UUID | None = None,
    ) -> dict[str, int]:
        """Get staging statistics with project scoping."""
        from sqlalchemy import func, select

        if project_ids is not None and len(project_ids) == 0:
            return {
                "pending_review": 0,
                "approved": 0,
                "rejected": 0,
                "changes_requested": 0,
                "total_staged": 0,
            }

        def _scope(q):
            if project_id:
                return q.where(Expense.project_id == project_id)
            elif project_ids is not None:
                return q.where(Expense.project_id.in_(project_ids))
            return q

        pending = await self.db.execute(
            _scope(select(func.count(Expense.id)).where(Expense.lifecycle_status == LifecycleStatus.STAGED))
        )
        approved = await self.db.execute(
            _scope(select(func.count(Expense.id)).where(Expense.lifecycle_status == LifecycleStatus.RECONCILED))
        )
        rejected = await self.db.execute(
            _scope(select(func.count(Expense.id)).where(Expense.lifecycle_status == LifecycleStatus.REJECTED))
        )
        needs_confirmation = await self.db.execute(
            _scope(select(func.count(Expense.id)).where(Expense.lifecycle_status == LifecycleStatus.NEEDS_CONFIRMATION))
        )

        return {
            "pending_review": pending.scalar() or 0,
            "approved": approved.scalar() or 0,
            "rejected": rejected.scalar() or 0,
            "changes_requested": needs_confirmation.scalar() or 0,
            "total_staged": (pending.scalar() or 0) + (approved.scalar() or 0) + (rejected.scalar() or 0) + (needs_confirmation.scalar() or 0),
        }


def create_staging_service(db: AsyncSession) -> StagingService:
    """Factory for creating StagingService."""
    return StagingService(db)
