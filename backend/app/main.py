from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.api.v1 import (
    audit,
    audit_compliance,
    auth,
    budgets,
    categories,
    evidence,
    expenses,
    extraction,
    health,
    monitoring,
    notification,
    ocr,
    payment_events,
    posting,
    projects,
    reconciliation,
    staging,
    vendors,
    webhooks,
)
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import CorrelationIdMiddleware, setup_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.security_headers import add_security_headers_middleware

setup_logging()

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


app = FastAPI(
    title="Construction Expense Management API",
    description="AI-Assisted Construction Expense Management System",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    lifespan=lifespan,
)

# CORS middleware with configurable origins
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# Security headers middleware
add_security_headers_middleware(
    app,
    csp_enabled=settings.SECURITY_HEADERS_CSP_ENABLED,
    hsts_enabled=settings.SECURITY_HEADERS_HSTS_ENABLED,
)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RateLimitMiddleware)

if settings.SENTRY_DSN:
    app.add_middleware(SentryAsgiMiddleware)  # type: ignore[arg-type]

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(projects.router, prefix=settings.API_V1_PREFIX)
app.include_router(expenses.router, prefix=settings.API_V1_PREFIX)
app.include_router(evidence.router, prefix=settings.API_V1_PREFIX)
app.include_router(ocr.router, prefix=settings.API_V1_PREFIX)
app.include_router(extraction.router, prefix=settings.API_V1_PREFIX)
app.include_router(staging.router, prefix=settings.API_V1_PREFIX)
app.include_router(reconciliation.router, prefix=settings.API_V1_PREFIX)
app.include_router(posting.router, prefix=settings.API_V1_PREFIX)
app.include_router(notification.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit_compliance.router, prefix=settings.API_V1_PREFIX)
app.include_router(monitoring.router, prefix=settings.API_V1_PREFIX)
app.include_router(webhooks.router, prefix=settings.API_V1_PREFIX)
app.include_router(categories.router, prefix=settings.API_V1_PREFIX)
app.include_router(vendors.router, prefix=settings.API_V1_PREFIX)
app.include_router(payment_events.router, prefix=settings.API_V1_PREFIX)
app.include_router(budgets.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)

register_exception_handlers(app)


@app.get("/")
async def root() -> dict:
    return {"message": "Construction Expense Management API", "version": "0.1.0"}