"""Audit compliance API endpoints for data retention, GDPR, and audit reporting."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_db_dep
from app.core.dependencies import get_current_user as get_current_user_dep, require_admin
from app.core.authorization import verify_project_access
from app.models.enums import GDPRRequestType
from app.models.user import User
from app.schemas.audit_compliance import (
    AuditReportRequest,
    ComplianceDashboardResponse,
    DataRetentionPolicyCreate,
    DataRetentionPolicyListResponse,
    DataRetentionPolicyResponse,
    GDPRRequestCreate,
    GDPRRequestListResponse,
    GDPRRequestResponse,
)
from app.services.audit_compliance import create_audit_compliance_service

router = APIRouter(prefix="/audit-compliance", tags=["audit-compliance"])


# ============ Data Retention Policies ============

@router.post(
    "/retention-policies",
    response_model=DataRetentionPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_retention_policy(
    request: DataRetentionPolicyCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> DataRetentionPolicyResponse:
    """Create a data retention policy."""

    service = create_audit_compliance_service(db)
    policy_id = await service.create_retention_policy(
        name=request.name,
        entity_types=request.entity_types,
        retention_days=request.retention_days,
        archive_after_days=request.archive_after_days,
        delete_after_days=request.delete_after_days,
        description=request.description,
        actor_id=current_user.id,
    )

    from app.models.audit_compliance import DataRetentionPolicy
    policy = await db.get(DataRetentionPolicy, policy_id)
    return DataRetentionPolicyResponse.model_validate(policy)


@router.get("/retention-policies", response_model=DataRetentionPolicyListResponse)
async def list_retention_policies(
    page: int = 1,
    page_size: int = 20,
    is_active: bool | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> DataRetentionPolicyListResponse:
    """List data retention policies."""

    service = create_audit_compliance_service(db)
    result = await service.list_retention_policies(
        page=page,
        page_size=page_size,
        is_active=is_active,
    )

    return DataRetentionPolicyListResponse(
        items=[DataRetentionPolicyResponse.model_validate(p) for p in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/retention-policies/{policy_id}", response_model=DataRetentionPolicyResponse)
async def get_retention_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> DataRetentionPolicyResponse:
    """Get a retention policy by ID."""
    from app.models.audit_compliance import DataRetentionPolicy

    policy = await db.get(DataRetentionPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    return DataRetentionPolicyResponse.model_validate(policy)


@router.patch("/retention-policies/{policy_id}", response_model=DataRetentionPolicyResponse)
async def update_retention_policy(
    policy_id: UUID,
    name: str | None = None,
    description: str | None = None,
    entity_types: list[str] | None = None,
    retention_days: int | None = None,
    archive_after_days: int | None = None,
    delete_after_days: int | None = None,
    is_active: bool | None = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> DataRetentionPolicyResponse:
    """Update a retention policy."""
    from app.models.audit_compliance import DataRetentionPolicy

    service = create_audit_compliance_service(db)
    policy_id = await service.update_retention_policy(
        policy_id=policy_id,
        name=name,
        description=description,
        entity_types=entity_types,
        retention_days=retention_days,
        archive_after_days=archive_after_days,
        delete_after_days=delete_after_days,
        is_active=is_active,
    )

    policy = await db.get(DataRetentionPolicy, policy_id)
    return DataRetentionPolicyResponse.model_validate(policy)


@router.post("/retention-policies/{policy_id}/run", response_model=dict)
async def run_retention_policy(
    policy_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Execute a data retention policy."""

    service = create_audit_compliance_service(db)
    try:
        results = await service.run_retention_policy(policy_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"results": results, "policy_id": str(policy_id)}


@router.post("/retention-policies/run-all", response_model=dict)
async def run_all_retention_policies(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Run all active retention policies."""

    service = create_audit_compliance_service(db)
    results = await service.run_all_retention_policies()
    return {"results": results}


# ============ GDPR Requests ============

@router.post("/gdpr-requests", response_model=GDPRRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_gdpr_request(
    request: GDPRRequestCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> GDPRRequestResponse:
    """Create a GDPR data subject request."""
    user_roles = {r.name for r in current_user.roles}
    target_user_id = request.user_id if ("admin" in user_roles and request.user_id) else current_user.id
    target_email = request.email if ("admin" in user_roles and request.email) else current_user.email

    service = create_audit_compliance_service(db)
    request_id = await service.create_gdpr_request(
        request_type=GDPRRequestType(request.request_type),
        user_id=target_user_id,
        email=target_email,
        description=request.description,
        actor_id=current_user.id,
    )

    from app.models.audit_compliance import GDPRRequest
    gdpr_request = await db.get(GDPRRequest, request_id)
    return GDPRRequestResponse.model_validate(gdpr_request)


@router.get("/gdpr-requests", response_model=GDPRRequestListResponse)
async def list_gdpr_requests(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    request_type: str | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> GDPRRequestListResponse:
    """List GDPR requests."""
    user_roles = {r.name for r in current_user.roles}
    target_user_id = None if "admin" in user_roles else current_user.id

    service = create_audit_compliance_service(db)
    result = await service.list_gdpr_requests(
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        request_type=request_type,
        user_id=target_user_id,
    )

    return GDPRRequestListResponse(
        items=[GDPRRequestResponse.model_validate(r) for r in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/gdpr-requests/{request_id}", response_model=GDPRRequestResponse)
async def get_gdpr_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> GDPRRequestResponse:
    """Get a GDPR request by ID."""
    service = create_audit_compliance_service(db)
    gdpr_request = await service.get_gdpr_request(request_id)
    if not gdpr_request:
        raise HTTPException(status_code=404, detail="GDPR request not found")

    user_roles = {r.name for r in current_user.roles}
    if "admin" not in user_roles and gdpr_request.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="GDPR request not found")

    return GDPRRequestResponse.model_validate(gdpr_request)


@router.post("/gdpr-requests/{request_id}/approve", response_model=GDPRRequestResponse)
async def approve_gdpr_request(
    request_id: UUID,
    response_data: dict[str, Any] | None = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> GDPRRequestResponse:
    """Approve a GDPR request."""

    service = create_audit_compliance_service(db)
    request_id = await service.process_gdpr_request(
        request_id=request_id,
        actor_id=current_user.id,
        action="approve",
        response_data=response_data,
    )

    from app.models.audit_compliance import GDPRRequest
    gdpr_request = await db.get(GDPRRequest, request_id)
    if not gdpr_request:
        raise HTTPException(status_code=404, detail="GDPR request not found")
    return GDPRRequestResponse.model_validate(gdpr_request)


@router.post("/gdpr-requests/{request_id}/reject", response_model=GDPRRequestResponse)
async def reject_gdpr_request(
    request_id: UUID,
    rejection_reason: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> GDPRRequestResponse:
    """Reject a GDPR request."""

    service = create_audit_compliance_service(db)
    request_id = await service.process_gdpr_request(
        request_id=request_id,
        actor_id=current_user.id,
        action="reject",
        rejection_reason=rejection_reason,
    )

    from app.models.audit_compliance import GDPRRequest
    gdpr_request = await db.get(GDPRRequest, request_id)
    return GDPRRequestResponse.model_validate(gdpr_request)


# ============ Audit Reports ============

@router.post("/reports", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def generate_audit_report(
    request: AuditReportRequest,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Generate an audit report."""
    user_roles = {r.name for r in current_user.roles}
    if "admin" not in user_roles:
        from app.models.expense import Expense
        if request.entity_type == "project" and request.entity_id:
            await verify_project_access(db, current_user, request.entity_id)
        elif request.entity_type == "expense" and request.entity_id:
            exp = await db.get(Expense, request.entity_id)
            if not exp:
                raise HTTPException(status_code=404, detail="Expense not found")
            await verify_project_access(db, current_user, exp.project_id)
        elif request.entity_type == "user" and request.entity_id:
            if request.entity_id != current_user.id:
                raise HTTPException(status_code=403, detail="Forbidden")
        elif request.report_type in ("system_changes", "data_access"):
            raise HTTPException(status_code=403, detail="Admin role required for system-level reports")

    service = create_audit_compliance_service(db)
    report_id = await service.generate_audit_report(
        report_type=request.report_type,
        date_from=request.date_from,
        date_to=request.date_to,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        user_id=current_user.id,
        format=request.format,
        include_payload=request.include_payload,
        actor_id=current_user.id,
    )

    return {"report_id": str(report_id), "status": "generating", "message": "Report generation started"}


@router.get("/reports", response_model=dict)
async def list_audit_reports(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    report_type: str | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """List audit reports."""
    user_roles = {r.name for r in current_user.roles}
    target_user_id = None if "admin" in user_roles else current_user.id

    service = create_audit_compliance_service(db)
    result = await service.list_audit_reports(
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        report_type=report_type,
        user_id=target_user_id,
    )

    return {
        "items": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


@router.get("/reports/{report_id}", response_model=dict)
async def get_audit_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Get audit report details."""
    from app.models.audit_compliance import AuditReport

    report = await db.get(AuditReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    user_roles = {r.name for r in current_user.roles}
    if "admin" not in user_roles and report.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": str(report.id),
        "report_type": report.report_type,
        "entity_type": report.entity_type,
        "entity_id": str(report.entity_id) if report.entity_id else None,
        "user_id": str(report.user_id) if report.user_id else None,
        "date_from": report.date_from.isoformat(),
        "date_to": report.date_to.isoformat(),
        "format": report.format,
        "include_payload": report.include_payload,
        "status": report.status,
        "record_count": report.record_count,
        "file_path": report.file_path,
        "file_size_bytes": report.file_size_bytes,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "expires_at": report.expires_at.isoformat() if report.expires_at else None,
        "created_at": report.created_at.isoformat(),
        "error_message": report.error_message,
    }


@router.get("/reports/{report_id}/download")
async def download_audit_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> FileResponse:
    """Download an audit report file."""
    from app.models.audit_compliance import AuditReport

    report = await db.get(AuditReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    user_roles = {r.name for r in current_user.roles}
    if "admin" not in user_roles and report.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Report not found")

    service = create_audit_compliance_service(db)
    try:
        file_path, format, file_size = await service.download_audit_report(report_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    media_type = "application/json" if format == "json" else "text/csv"
    filename = f"audit_report_{report_id}.{format}"
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )


# ============ Audit Trail ============

@router.get("/trail/{entity_type}/{entity_id}", response_model=dict)
async def get_audit_trail(
    entity_type: str,
    entity_id: UUID,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict[str, Any]:
    """Get complete audit trail for an entity."""
    from sqlalchemy import func, select

    from app.models.audit_event import AuditEvent

    # Authorization scoping for entity
    from app.models.expense import Expense
    from app.models.project import Project

    if entity_type == "project":
        await verify_project_access(db, current_user, entity_id)
    elif entity_type == "expense":
        exp = await db.get(Expense, entity_id)
        if not exp:
            raise HTTPException(status_code=404, detail="Expense not found")
        await verify_project_access(db, current_user, exp.project_id)
    elif entity_type == "user":
        user_roles = {r.name for r in current_user.roles}
        if "admin" not in user_roles and current_user.id != entity_id:
            raise HTTPException(status_code=403, detail="Forbidden")

    # Total count
    query = select(AuditEvent).where(
        AuditEvent.entity_type == entity_type,
        AuditEvent.entity_id == entity_id,
    )
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = select(AuditEvent).where(
        AuditEvent.entity_type == entity_type,
        AuditEvent.entity_id == entity_id,
    ).order_by(AuditEvent.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    events = result.scalars().all()

    # Get first and last event times
    first_event = await db.execute(
        select(AuditEvent.created_at).where(
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
        ).order_by(AuditEvent.created_at.asc()).limit(1)
    )
    last_event = await db.execute(
        select(AuditEvent.created_at).where(
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == entity_id,
        ).order_by(AuditEvent.created_at.desc()).limit(1)
    )

    first_at = first_event.scalar()
    last_at = last_event.scalar()

    from app.schemas.audit_compliance import AuditEventResponse

    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "events": [AuditEventResponse.model_validate(e) for e in events],
        "total_events": total,
        "page": page,
        "page_size": page_size,
        "first_event_at": first_at.isoformat() if first_at else None,
        "last_event_at": last_at.isoformat() if last_at else None,
    }


# ============ Compliance Dashboard ============

@router.get("/dashboard", response_model=ComplianceDashboardResponse)
async def get_compliance_dashboard(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> ComplianceDashboardResponse:
    """Get compliance dashboard overview."""

    service = create_audit_compliance_service(db)
    stats = await service.get_compliance_dashboard()
    return ComplianceDashboardResponse(**stats)
