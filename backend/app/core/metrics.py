"""Prometheus metrics and monitoring utilities."""

import time
import functools
from typing import Callable, Any
from contextlib import asynccontextmanager

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

# Create custom registry
registry = CollectorRegistry()

# HTTP Request Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry,
)

# Database Metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query latency in seconds",
    ["query_type", "table"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=registry,
)

db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections",
    registry=registry,
)

db_connections_idle = Gauge(
    "db_connections_idle",
    "Number of idle database connections",
    registry=registry,
)

# Celery Task Metrics
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total Celery tasks",
    ["task_name", "status", "queue"],
    registry=registry,
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task duration in seconds",
    ["task_name", "queue"],
    buckets=[1, 5, 10, 30, 60, 60, 300, 600, 1800, 3600],
    registry=registry,
)

celery_tasks_active = Gauge(
    "celery_tasks_active",
    "Number of active Celery tasks",
    ["queue"],
    registry=registry,
)

celery_workers_online = Gauge(
    "celery_workers_online",
    "Number of online Celery workers",
    registry=registry,
)

# Business Metrics
expenses_created_total = Counter(
    "expenses_created_total",
    "Total expenses created",
    ["project_id", "status"],
    registry=registry,
)

expenses_amount_total = Counter(
    "expenses_amount_total",
    "Total expense amount in cents",
    ["project_id", "currency"],
    registry=registry,
)

expenses_reconciled_total = Counter(
    "expenses_reconciled_total",
    "Total expenses reconciled",
    ["project_id", "match_basis"],
    registry=registry,
)

reconciliation_matches_total = Counter(
    "reconciliation_matches_total",
    "Total reconciliation matches",
    ["project_id", "match_basis"],
    registry=registry,
)

reconciliation_amount_matched = Counter(
    "reconciliation_amount_matched",
    "Total amount reconciled in cents",
    ["currency"],
    registry=registry,
)

webhook_deliveries_total = Counter(
    "webhook_deliveries_total",
    "Total webhook delivery attempts",
    ["webhook_id", "success"],
    registry=registry,
)

webhook_delivery_duration_seconds = Histogram(
    "webhook_delivery_duration_seconds",
    "Webhook delivery duration in seconds",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
    registry=registry,
)

notification_sent_total = Counter(
    "notification_sent_total",
    "Total notifications sent",
    ["channel", "status"],
    registry=registry,
)

notification_delivery_duration_seconds = Histogram(
    "notification_delivery_duration_seconds",
    "Notification delivery duration in seconds",
    ["channel"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
    registry=registry,
)

# Retention Policy Metrics
retention_policies_executed_total = Counter(
    "retention_policies_executed_total",
    "Total retention policies executed",
    ["policy_id", "status"],
    registry=registry,
)

records_archived_total = Counter(
    "records_archived_total",
    "Total records archived",
    ["entity_type"],
    registry=registry,
)

records_deleted_total = Counter(
    "records_deleted_total",
    "Total records deleted",
    ["entity_type"],
    registry=registry,
)

# GDPR Request Metrics
gdpr_requests_total = Counter(
    "gdpr_requests_total",
    "Total GDPR requests",
    ["request_type", "status"],
    registry=registry,
)

# Audit Report Metrics
audit_reports_generated_total = Counter(
    "audit_reports_generated_total",
    "Total audit reports generated",
    ["report_type", "format", "status"],
    registry=registry,
)

audit_report_generation_duration_seconds = Histogram(
    "audit_report_generation_duration_seconds",
    "Audit report generation duration in seconds",
    ["report_type", "format"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=registry,
)

# System Metrics
active_users = Gauge(
    "active_users",
    "Number of active users in the last 5 minutes",
    registry=registry,
)

api_keys_active = Gauge(
    "api_keys_active",
    "Number of active API keys",
    registry=registry,
)

# Health Check Metrics
health_check_duration_seconds = Histogram(
    "health_check_duration_seconds",
    "Health check duration in seconds",
    ["service"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
    registry=registry,
)

service_health_status = Gauge(
    "service_health_status",
    "Service health status (1=healthy, 0=unhealthy)",
    ["service"],
    registry=registry,
)

# Custom registry for metrics endpoint
def get_metrics_registry() -> "prometheus_client.CollectorRegistry":
    """Get the metrics registry."""
    return registry


def metrics_endpoint() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest(registry)


def get_content_type() -> str:
    """Get the content type for metrics endpoint."""
    return CONTENT_TYPE_LATEST


# Middleware for request metrics
class MetricsMiddleware:
    """Middleware to collect HTTP request metrics."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        start_time = time.time()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                duration = time.time() - start_time
                
                # Record metrics
                http_requests_total.labels(
                    method=method,
                    endpoint=path,
                    status=status_code,
                ).inc()
                
                http_request_duration_seconds.labels(
                    method=method,
                    endpoint=path,
                ).observe(duration)
            await send(message)
        
        await self.app(scope, receive, send_wrapper)


# Decorators for timing functions
def track_db_query(query_type: str, table: str):
    """Decorator to track database query duration."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                db_query_duration_seconds.labels(
                    query_type=query_type,
                    table=table,
                ).observe(duration)
        return async_wrapper
    return decorator


def track_celery_task(task_name: str, queue: str = "default"):
    """Decorator to track Celery task metrics."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            celery_tasks_active.labels(queue=queue).inc()
            start = time.perf_counter()
            status = "success"
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                status = "failure"
                raise
            finally:
                duration = time.perf_counter() - start
                celery_tasks_total.labels(
                    task_name=task_name,
                    status=status,
                    queue=queue,
                ).inc()
                celery_task_duration_seconds.labels(
                    task_name=task_name,
                    queue=queue,
                ).observe(duration)
                celery_tasks_active.labels(queue=queue).dec()
        return async_wrapper
    return decorator


# Health check utilities
async def check_database_health(db_session) -> dict:
    """Check database connectivity."""
    start = time.perf_counter()
    try:
        await db_session.execute(text("SELECT 1"))
        duration = time.perf_counter() - start
        health_check_duration_seconds.labels(service="database").observe(duration)
        service_health_status.labels(service="database").set(1)
        return {"status": "healthy", "duration_ms": duration * 1000}
    except Exception as e:
        duration = time.perf_counter() - start
        health_check_duration_seconds.labels(service="database").observe(duration)
        service_health_status.labels(service="database").set(0)
        return {"status": "unhealthy", "error": str(e), "duration_ms": duration * 1000}


async def check_redis_health(redis_client) -> dict:
    """Check Redis connectivity."""
    start = time.perf_counter()
    try:
        await redis_client.ping()
        duration = time.perf_counter() - start
        health_check_duration_seconds.labels(service="redis").observe(duration)
        service_health_status.labels(service="redis").set(1)
        return {"status": "healthy", "duration_ms": duration * 1000}
    except Exception as e:
        duration = time.perf_counter() - start
        health_check_duration_seconds.labels(service="redis").observe(duration)
        service_health_status.labels(service="redis").set(0)
        return {"status": "unhealthy", "error": str(e), "duration_ms": duration * 1000}


async def check_minio_health(minio_client) -> dict:
    """Check MinIO connectivity."""
    start = time.perf_counter()
    try:
        minio_client.list_buckets()
        duration = time.perf_counter() - start
        health_check_duration_seconds.labels(service="minio").observe(duration)
        service_health_status.labels(service="minio").set(1)
        return {"status": "healthy", "duration_ms": duration * 1000}
    except Exception as e:
        duration = time.perf_counter() - start
        health_check_duration_seconds.labels(service="minio").observe(duration)
        service_health_status.labels(service="minio").set(0)
        return {"status": "unhealthy", "error": str(e), "duration_ms": duration * 1000}


async def check_celery_health(celery_app) -> dict:
    """Check Celery worker health."""
    start = time.perf_counter()
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        active = inspect.active()
        
        if stats:
            duration = time.perf_counter() - start
            health_check_duration_seconds.labels(service="celery").observe(duration)
            service_health_status.labels(service="celery").set(1)
            
            # Update worker gauge
            celery_workers_online.set(len(stats))
            
            # Update active tasks per queue
            if active:
                queue_counts = {}
                for worker, tasks in active.items():
                    for task in tasks:
                        queue = task.get("delivery_info", {}).get("routing_key", "default")
                        queue_counts[queue] = queue_counts.get(queue, 0) + 1
                
                for queue, count in queue_counts.items():
                    celery_tasks_active.labels(queue=queue).set(count)
            
            return {
                "status": "healthy",
                "workers": len(stats),
                "duration_ms": duration * 1000,
            }
        else:
            duration = time.perf_counter() - start
            health_check_duration_seconds.labels(service="celery").observe(duration)
            service_health_status.labels(service="celery").set(0)
            return {"status": "unhealthy", "error": "No workers online"}
    except Exception as e:
        duration = time.perf_counter() - start
        health_check_duration_seconds.labels(service="celery").observe(duration)
        service_health_status.labels(service="celery").set(0)
        return {"status": "unhealthy", "error": str(e), "duration_ms": duration * 1000}