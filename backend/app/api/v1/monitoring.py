"""Monitoring and health check endpoints."""

from typing import Any
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_db, get_redis, get_minio
from app.core.dependencies import require_admin
from app.models.user import User
from app.core.metrics import (
    metrics_endpoint,
    get_content_type,
    check_database_health,
    check_redis_health,
    check_minio_health,
    check_celery_health,
)
from app.core.celery_app import celery_app

router = APIRouter(tags=["monitoring"])


@router.get("/health", tags=["health"])
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "construction-expense-api",
        "version": "0.1.0",
    }


@router.get("/health/detailed", tags=["health"])
async def detailed_health_check(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Detailed health check with all dependencies."""
    redis = await get_redis()
    minio = get_minio()
    
    checks = {
        "database": await check_database_health(db),
        "redis": await check_redis_health(redis),
        "minio": await check_minio_health(minio),
        "celery": await check_celery_health(celery_app),
    }
    
    all_healthy = all(check.get("status") == "healthy" for check in checks.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
    }


@router.get("/health/ready", tags=["health"])
async def readiness_check(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kubernetes readiness probe."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}


@router.get("/health/live", tags=["health"])
async def liveness_check() -> dict:
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get("/metrics", tags=["metrics"])
async def prometheus_metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=metrics_endpoint(),
        media_type=get_content_type(),
    )


@router.get("/metrics/system", tags=["metrics"])
async def system_metrics(
    current_user: User = Depends(require_admin),
) -> dict:
    """Get system-level metrics."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    cpu_percent = process.cpu_percent(interval=0.1)
    
    disk = psutil.disk_usage('/')
    
    return {
        "process": {
            "pid": os.getpid(),
            "memory_rss_mb": memory_info.rss / 1024 / 1024,
            "memory_vms_mb": memory_info.vms / 1024 / 1024,
            "cpu_percent": cpu_percent,
            "threads": process.num_threads(),
            "open_files": len(process.open_files()),
            "connections": len(process.connections()),
        },
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_available_mb": psutil.virtual_memory().available / 1024 / 1024,
            "disk_percent": disk.percent,
            "disk_free_gb": disk.free / 1024 / 1024 / 1024,
        },
    }


@router.get("/metrics/celery", tags=["metrics"])
async def celery_metrics(
    current_user: User = Depends(require_admin),
) -> dict:
    """Get Celery worker metrics."""
    from app.core.celery_app import celery_app
    
    inspect = celery_app.control.inspect()
    
    stats = inspect.stats()
    active = inspect.active()
    scheduled = inspect.scheduled()
    reserved = inspect.reserved()
    
    workers = {}
    if stats:
        for worker, stat in stats.items():
            worker_active = active.get(worker, []) if active else []
            worker_scheduled = scheduled.get(worker, []) if scheduled else []
            worker_reserved = reserved.get(worker, []) if reserved else []
            
            workers[worker] = {
                "stats": stat,
                "active_tasks": len(worker_active),
                "scheduled_tasks": len(worker_scheduled),
                "reserved_tasks": len(worker_reserved),
                "pool": stat.get("pool", {}),
                "loadavg": stat.get("loadavg", []),
            }
    
    return {
        "workers": workers,
        "total_workers": len(stats) if stats else 0,
    }


@router.get("/metrics/business", tags=["metrics"])
async def business_metrics_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict:
    """Get business metrics."""
    from sqlalchemy import func, select, String
    from app.models.expense import Expense
    from app.models.project import Project
    from app.models.reconciliation_record import ReconciliationRecord
    from app.models.payment_event import PaymentEvent
    
    try:
        # Total expenses
        total_expenses = await db.scalar(select(func.count(Expense.id)))
        
        # Total amount
        total_amount = await db.scalar(select(func.sum(Expense.total)))
        
        # By status
        status_counts = {}
        for status in ["RECEIVED", "VALIDATED", "PROCESSING", "EXTRACTED", "RECONCILED", "POSTED", "FAILED"]:
            count = await db.scalar(
                select(func.count(Expense.id)).where(Expense.lifecycle_status.cast(String) == status)
            )
            status_counts[status] = count or 0
        
        # Total projects
        total_projects = await db.scalar(select(func.count(Project.id)))
        active_projects = await db.scalar(
            select(func.count(Project.id)).where(Project.status.cast(String) == "active")
        )
        
        # Reconciliation stats
        total_reconciled = await db.scalar(
            select(func.count(ReconciliationRecord.id)).where(
                ReconciliationRecord.status.cast(String) == "MATCHED"
            )
        )
        
        pending_reconciliation = await db.scalar(
            select(func.count(ReconciliationRecord.id)).where(
                ReconciliationRecord.status.cast(String) == "UNMATCHED"
            )
        )
        
        # Payment events
        total_payments = await db.scalar(select(func.count(PaymentEvent.id)))
        total_payment_amount = await db.scalar(select(func.sum(PaymentEvent.amount)))
        
        return {
            "expenses": {
                "total": total_expenses or 0,
                "total_amount": float(total_amount or 0),
                "by_status": status_counts,
            },
            "projects": {
                "total": total_projects or 0,
                "active": active_projects or 0,
            },
            "reconciliation": {
                "matched": total_reconciled or 0,
                "pending": pending_reconciliation or 0,
            },
            "payments": {
                "total": total_payments or 0,
                "total_amount": float(total_payment_amount or 0),
            },
        }
    except Exception as e:
        return {"error": str(e)}