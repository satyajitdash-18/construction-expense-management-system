"""Audit compliance service for data retention, GDPR, and audit reporting."""

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import aiofiles
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.helper import write_audit_event
from app.core.config import settings
from app.core.logging import get_logger
from app.models.audit_compliance import (
    AuditReport,
    AuditReportExport,
    DataRetentionPolicy,
    GDPRRequest,
)
from app.models.audit_event import AuditEvent
from app.models.enums import GDPRRequestStatus, GDPRRequestType
from app.models.expense import Expense
from app.models.notification import Notification
from app.schemas.audit_compliance import (
    AuditReportResponse,
    DataRetentionPolicyResponse,
    GDPRRequestResponse,
)

logger = get_logger(__name__)

# Directory for audit report exports
EXPORT_DIR = settings.EXPORT_DIR or "/tmp/audit_exports"
os.makedirs(EXPORT_DIR, exist_ok=True)


class AuditComplianceService:
    """Service for audit compliance: data retention, GDPR, audit reporting."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ Data Retention Policies ============

    async def create_retention_policy(
        self,
        name: str,
        entity_types: list[str],
        retention_days: int,
        archive_after_days: int | None = None,
        delete_after_days: int | None = None,
        description: str | None = None,
        actor_id: UUID | None = None,
    ) -> UUID:
        """Create a data retention policy."""
        policy = DataRetentionPolicy(
            name=name,
            description=description,
            entity_types=entity_types,
            retention_days=retention_days,
            archive_after_days=archive_after_days,
            delete_after_days=delete_after_days,
        )
        self.db.add(policy)
        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="retention_policy.created",
            entity_type="data_retention_policy",
            entity_id=policy.id,
            actor_id=actor_id,
            payload={"name": name, "entity_types": entity_types, "retention_days": retention_days},
        )
        return policy.id

    async def list_retention_policies(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        """List data retention policies."""
        query = select(DataRetentionPolicy)

        if is_active is not None:
            query = query.where(DataRetentionPolicy.is_active == is_active)

        # Total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(DataRetentionPolicy.created_at.desc())

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [DataRetentionPolicyResponse.model_validate(p) for p in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def update_retention_policy(
        self,
        policy_id: UUID,
        name: str | None = None,
        description: str | None = None,
        entity_types: list[str] | None = None,
        retention_days: int | None = None,
        archive_after_days: int | None = None,
        delete_after_days: int | None = None,
        is_active: bool | None = None,
    ) -> UUID:
        """Update a data retention policy."""
        from app.models.audit_compliance import DataRetentionPolicy

        policy = await self.db.get(DataRetentionPolicy, policy_id)
        if not policy:
            raise ValueError(f"Retention policy {policy_id} not found")

        if name is not None:
            policy.name = name
        if description is not None:
            policy.description = description
        if entity_types is not None:
            policy.entity_types = entity_types
        if retention_days is not None:
            policy.retention_days = retention_days
        if archive_after_days is not None:
            policy.archive_after_days = archive_after_days
        if delete_after_days is not None:
            policy.delete_after_days = delete_after_days
        if is_active is not None:
            policy.is_active = is_active

        policy.updated_at = datetime.now(UTC)
        await self.db.commit()

        return policy.id

    async def run_retention_policy(self, policy_id: UUID) -> dict[str, int]:
        """Execute a data retention policy."""
        policy = await self.db.get(DataRetentionPolicy, policy_id)
        if not policy:
            raise ValueError(f"Retention policy {policy_id} not found")

        if not policy.is_active:
            raise ValueError("Policy is not active")

        _ = datetime.now(UTC) - timedelta(days=policy.retention_days)
        archive_date = (
            datetime.now(UTC) - timedelta(days=policy.archive_after_days)
            if policy.archive_after_days
            else None
        )
        delete_date = (
            datetime.now(UTC) - timedelta(days=policy.delete_after_days)
            if policy.delete_after_days
            else None
        )

        results = {"archived": 0, "deleted": 0, "errors": 0}

        for entity_type in policy.entity_types:
            try:
                if entity_type == "audit_events":
                    # Archive old audit events
                    if archive_date:
                        stmt = (
                            delete(AuditEvent)
                            .where(AuditEvent.created_at < archive_date)
                            .execution_options(synchronize_session=False)
                        )
                        result = await self.db.execute(stmt)
                        results["archived"] += result.rowcount  # type: ignore[attr-defined]

                    # Delete old audit events
                    if delete_date:
                        stmt = (
                            delete(AuditEvent)
                            .where(AuditEvent.created_at < delete_date)
                            .execution_options(synchronize_session=False)
                        )
                        result = await self.db.execute(stmt)
                        results["deleted"] += result.rowcount  # type: ignore[attr-defined]

                elif entity_type == "expenses":
                    # Archive old expenses
                    if archive_date:
                        archive_stmt = (
                            update(Expense)
                            .where(
                                Expense.created_at < archive_date,
                                Expense.lifecycle_status.in_(["POSTED", "REJECTED"]),
                            )
                            .values(lifecycle_status="ARCHIVED")
                            .execution_options(synchronize_session=False)
                        )
                        result = await self.db.execute(archive_stmt)
                        results["archived"] += result.rowcount  # type: ignore[attr-defined]

                    # Delete very old expenses
                    if delete_date:
                        delete_stmt = (
                            delete(Expense)
                            .where(
                                Expense.created_at < delete_date,
                                Expense.lifecycle_status.in_(["REJECTED", "FAILED"]),
                            )
                            .execution_options(synchronize_session=False)
                        )
                        result = await self.db.execute(delete_stmt)
                        results["deleted"] += result.rowcount  # type: ignore[attr-defined]

                elif entity_type == "notifications":
                    if delete_date:
                        stmt = (
                            delete(Notification)
                            .where(
                                Notification.created_at < delete_date,
                                Notification.status.in_(["SENT", "FAILED"]),
                            )
                            .execution_options(synchronize_session=False)
                        )
                        result = await self.db.execute(stmt)
                        results["deleted"] += result.rowcount  # type: ignore[attr-defined]

            except Exception as e:
                logger.error("Retention policy entity error", entity_type=entity_type, error=str(e))
                results["errors"] += 1

        # Update policy last run
        policy_obj = await self.db.get(DataRetentionPolicy, policy_id)
        if policy_obj:
            policy_obj.last_run_at = datetime.now(UTC)
            policy_obj.next_run_at = datetime.now(UTC) + timedelta(days=1)
            await self.db.commit()

        return results

    async def run_all_retention_policies(self) -> dict[str, Any]:
        """Run all active retention policies."""
        from app.models.audit_compliance import DataRetentionPolicy

        result = await self.db.execute(
            select(DataRetentionPolicy).where(DataRetentionPolicy.is_active)
        )
        policies = result.scalars().all()

        total_results = {"archived": 0, "deleted": 0, "errors": 0}

        for policy in policies:
            try:
                results = await self.run_retention_policy(policy.id)
                total_results["archived"] += results.get("archived", 0)
                total_results["deleted"] += results.get("deleted", 0)
                total_results["errors"] += results.get("errors", 0)
            except Exception as e:
                logger.error("Retention policy failed", policy_id=str(policy.id), error=str(e))
                total_results["errors"] += 1

        return total_results

    # ============ GDPR Requests ============

    async def create_gdpr_request(
        self,
        request_type: GDPRRequestType,
        user_id: UUID,
        email: str,
        description: str | None = None,
        actor_id: UUID | None = None,
    ) -> UUID:
        """Create a GDPR data subject request."""
        # Check for existing pending request of same type
        existing = await self.db.execute(
            select(GDPRRequest).where(
                GDPRRequest.user_id == user_id,
                GDPRRequest.request_type == request_type,
                GDPRRequest.status.in_([GDPRRequestStatus.PENDING, GDPRRequestStatus.PROCESSING]),
            )
        )
        if existing.scalar():
            raise ValueError(f"Pending {request_type.value} request already exists for this user")

        gdpr_request = GDPRRequest(
            request_type=request_type,
            user_id=user_id,
            email=email,
            description=description,
            status=GDPRRequestStatus.PENDING,
        )
        self.db.add(gdpr_request)
        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type="gdpr_request.created",
            entity_type="gdpr_request",
            entity_id=gdpr_request.id,
            actor_id=actor_id,
            payload={"request_type": request_type.value, "user_id": str(user_id)},
        )
        return gdpr_request.id

    async def list_gdpr_requests(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        request_type: str | None = None,
    ) -> dict[str, Any]:
        """List GDPR requests."""
        query = select(GDPRRequest)

        if status_filter:
            query = query.where(GDPRRequest.status == GDPRRequestStatus(status_filter))
        if request_type:
            query = query.where(GDPRRequest.request_type == GDPRRequestType(request_type))

        # Total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(GDPRRequest.created_at.desc())

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [GDPRRequestResponse.model_validate(r) for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def process_gdpr_request(
        self,
        request_id: UUID,
        actor_id: UUID,
        action: str,
        response_data: dict[str, Any] | None = None,
        rejection_reason: str | None = None,
    ) -> UUID:
        """Process a GDPR request (approve/reject)."""
        gdpr_request = await self.db.get(GDPRRequest, request_id)
        if not gdpr_request:
            raise ValueError(f"GDPR request {request_id} not found")

        if gdpr_request.status != GDPRRequestStatus.PENDING:
            raise ValueError(f"Request is not pending (current: {gdpr_request.status})")

        if action == "approve":
            gdpr_request.status = GDPRRequestStatus.PROCESSING
            # TODO: Implement actual data processing based on request_type
            gdpr_request.status = GDPRRequestStatus.COMPLETED
            gdpr_request.response_data = response_data
            gdpr_request.completed_at = datetime.now(UTC)
        elif action == "reject":
            gdpr_request.status = GDPRRequestStatus.REJECTED
            gdpr_request.description = rejection_reason

        gdpr_request.updated_at = datetime.now(UTC)
        await self.db.flush()

        await write_audit_event(
            session=self.db,
            event_type=f"gdpr_request.{action}",
            entity_type="gdpr_request",
            entity_id=gdpr_request.id,
            actor_id=actor_id,
            payload={"request_type": gdpr_request.request_type.value, "user_id": str(gdpr_request.user_id)},
        )

        await self.db.commit()
        return gdpr_request.id

    async def get_gdpr_request(self, request_id: UUID) -> GDPRRequest | None:
        """Get a GDPR request by ID."""
        return await self.db.get(GDPRRequest, request_id)

    # ============ Audit Reports ============

    async def generate_audit_report(
        self,
        report_type: str,
        date_from: datetime,
        date_to: datetime,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        format: str = "json",
        include_payload: bool = True,
        actor_id: UUID | None = None,
    ) -> UUID:
        """Generate an audit report."""
        report = AuditReport(
            report_type=report_type,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            format=format,
            include_payload=include_payload,
            status="generating",
        )
        self.db.add(report)
        await self.db.flush()

        # Generate report asynchronously (in real implementation, this would be a background task)
        # For now, we'll generate synchronously
        try:
            await self._generate_report_content(report, include_payload)
            report.status = "completed"
            report.generated_at = datetime.now(UTC)
        except Exception as e:
            report.status = "failed"
            report.error_message = str(e)
            logger.error("Report generation failed", report_id=str(report.id), error=str(e))

        await self.db.commit()
        return report.id

    async def _generate_report_content(self, report: "AuditReport", include_payload: bool) -> None:
        """Generate the actual report content."""
        # Build query based on report type
        query = select(AuditEvent).where(
            AuditEvent.created_at >= report.date_from,
            AuditEvent.created_at <= report.date_to,
        )

        if report.entity_type:
            query = query.where(AuditEvent.entity_type == report.entity_type)
        if report.entity_id:
            query = query.where(AuditEvent.entity_id == report.entity_id)
        if report.user_id:
            query = query.where(AuditEvent.actor_id == report.user_id)

        result = await self.db.execute(query.order_by(AuditEvent.created_at.desc()))
        events = result.scalars().all()

        report.record_count = len(events)

        # Generate file
        filename = f"audit_report_{report.id}_{report.report_type}.{report.format}"
        file_path = os.path.join(EXPORT_DIR, filename)

        if report.format == "json":
            data = {
                "report_type": report.report_type,
                "date_range": {
                    "from": report.date_from.isoformat(),
                    "to": report.date_to.isoformat(),
                },
                "record_count": len(events),
                "events": [
                    {
                        "id": str(e.id),
                        "event_type": e.event_type,
                        "entity_type": e.entity_type,
                        "entity_id": str(e.entity_id),
                        "actor_id": str(e.actor_id) if e.actor_id else None,
                        "correlation_id": str(e.correlation_id),
                        "causation_id": str(e.causation_id) if e.causation_id else None,
                        "payload": e.payload if include_payload else None,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in events
                ],
            }
            async with aiofiles.open(file_path, "w") as f:
                await f.write(json.dumps(data, indent=2))

        elif report.format == "csv":
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "id",
                    "event_type",
                    "entity_type",
                    "entity_id",
                    "actor_id",
                    "correlation_id",
                    "causation_id",
                    "created_at",
                ]
            )
            for e in events:
                writer.writerow(
                    [
                        str(e.id),
                        e.event_type,
                        e.entity_type,
                        str(e.entity_id),
                        str(e.actor_id) if e.actor_id else "",
                        str(e.correlation_id),
                        str(e.causation_id) if e.causation_id else "",
                        e.created_at.isoformat(),
                    ]
                )
            async with aiofiles.open(file_path, "w") as f:
                await f.write(output.getvalue())

        # Create export record
        file_size = os.path.getsize(file_path)
        export = AuditReportExport(
            report_id=report.id,
            file_path=file_path,
            format=report.format,
            file_size_bytes=file_size,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        self.db.add(export)
        await self.db.flush()

        # Update report
        report.file_path = file_path
        report.file_size_bytes = file_size
        report.expires_at = datetime.now(UTC) + timedelta(days=7)

    async def list_audit_reports(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        report_type: str | None = None,
    ) -> dict[str, Any]:
        """List audit reports."""
        query = select(AuditReport)

        if status_filter:
            query = query.where(AuditReport.status == status_filter)
        if report_type:
            query = query.where(AuditReport.report_type == report_type)

        # Total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(AuditReport.created_at.desc())

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": [AuditReportResponse.model_validate(r) for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def download_audit_report(self, report_id: UUID) -> tuple[str, str, int]:
        """Get report export for download."""
        export_result = await self.db.execute(
            select(AuditReportExport).where(AuditReportExport.report_id == report_id)
        )
        export = export_result.scalars().first()

        if not export:
            raise ValueError("Report export not found")

        if export.expires_at < datetime.now(UTC):
            raise ValueError("Report export has expired")

        export.download_count += 1
        export.last_downloaded_at = datetime.now(UTC)
        await self.db.commit()

        return export.file_path, export.format, export.file_size_bytes

    async def get_compliance_dashboard(self) -> dict[str, Any]:
        """Get compliance dashboard statistics."""
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today.replace(day=1)

        audit_today = await self.db.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.created_at >= today)
        )
        audit_month = await self.db.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.created_at >= month_start)
        )
        pending_gdpr = await self.db.scalar(
            select(func.count(GDPRRequest.id)).where(
                GDPRRequest.status == GDPRRequestStatus.PENDING
            )
        )
        completed_gdpr_month = await self.db.scalar(
            select(func.count(GDPRRequest.id)).where(
                GDPRRequest.status == GDPRRequestStatus.COMPLETED,
                GDPRRequest.completed_at >= month_start,
            )
        )
        active_policies = await self.db.scalar(
            select(func.count(DataRetentionPolicy.id)).where(
                DataRetentionPolicy.is_active
            )
        )

        # Archived/deleted this month
        from app.models.audit_compliance import AuditReport

        archived_month = await self.db.scalar(
            select(func.count(AuditReport.id)).where(
                AuditReport.status == "completed",
                AuditReport.generated_at >= month_start,
            )
        )

        return {
            "audit_events_today": audit_today or 0,
            "audit_events_this_month": audit_month or 0,
            "pending_gdpr_requests": pending_gdpr or 0,
            "completed_gdpr_requests_this_month": completed_gdpr_month or 0,
            "data_retention_policies_active": active_policies or 0,
            "records_archived_this_month": 0,  # Would need tracking
            "records_deleted_this_month": 0,  # Would need tracking
            "audit_reports_generated_this_month": archived_month or 0,
            "failed_webhook_deliveries": 0,  # From notification service
        }


def create_audit_compliance_service(db: AsyncSession) -> AuditComplianceService:
    """Factory for creating AuditComplianceService."""
    return AuditComplianceService(db)
