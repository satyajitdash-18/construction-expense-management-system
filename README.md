# Construction Expense Management System

AI-Assisted Construction Expense Management System for tracking, reconciling, and reporting construction project expenses with double-entry ledger integrity.

## Key Capabilities

- **Multi-source expense ingestion**: Manual entry, WhatsApp Business API, OCR receipt processing, bank feed imports
- **AI-powered extraction**: LLM-based (OpenAI, Gemini, Anthropic) receipt data extraction with confidence scoring
- **Automated reconciliation**: Multi-tier matching (reference -> scored -> manual) between expenses and bank feeds
- **Double-entry ledger**: Double-entry ledger with debit/credit invariant enforcement and GST tax handling.
- **Full audit trail**: Immutable event sourcing with correlation/causation chains with compliance-oriented audit reporting
- **Role-based access**: Admin, Project Manager, Finance User, Site User with project-scoped permissions
- **Project isolation**: Project-scoped access and permissions with budgets, vendors, and categories per project
- **OCR pipeline**: Tesseract-based receipt text extraction -> LLM structured extraction -> expense creation
- **WhatsApp integration**: Cloud API webhook processing for text/media messages
- **Notification system**: Multi-channel (email, SMS, WhatsApp, push, webhook) with preferences and webhooks
- **Compliance-oriented auditing**: Data retention policies, user data export/erasure request workflows, automated compliance-oriented audit report generation
- **Prometheus metrics**: Health checks, performance monitoring, structured logging

## Architecture Overview

```
+-----------------+     +------------------+     +-----------------+
|   Frontend      |---->|    Backend API   |---->|   PostgreSQL    |
|  (React/Vite)   |     |   (FastAPI)      |     |   (AsyncPG)     |
+-----------------+     +--------+---------+     +-----------------+
                                 |
           +---------------------+---------------------+
           |                     |                     |
           v                     v                     v
    +-------------+      +-------------+       +-------------+
    |    Redis    |      |    MinIO    |       |   Celery    |
    |  (Cache/    |      | (Object     |       | (Workers/   |
    |   Queue)    |      |  Storage)   |       |   Beat)     |
    +-------------+      +-------------+       +-------------+
                                 |                     |
                                 v                     v
                          +-------------+       +-------------+
                          |   LLM       |       |  Scheduled  |
                          |  Providers  |       |  Tasks      |
                          | (OpenAI/    |       | (Retention, |
                          |  Gemini/    |       |  Reports,   |
                          |  Anthropic) |       |  Cleanup)   |
                          +-------------+       +-------------+
```

## Technology Stack

### Frontend
- **Framework**: React 18 + TypeScript + Vite
- **State**: Zustand + TanStack Query (React Query)
- **UI**: Radix UI primitives + Tailwind CSS
- **Forms**: React Hook Form + Zod validation
- **Routing**: React Router v7
- **Charts**: Recharts
- **API Client**: Axios + OpenAPI-generated client
- **Linting**: ESLint + TypeScript ESLint

### Backend
- **Framework**: FastAPI 0.115 (async)
- **Python**: 3.12 (strict typing with mypy)
- **ORM**: SQLAlchemy 2.0 (async) + Alembic migrations
- **Validation**: Pydantic v2 + pydantic-settings
- **Auth**: JWT (HS256) access/refresh tokens with rotation & revocation
- **Password Hashing**: Argon2 / bcrypt via passlib
- **Rate Limiting**: Redis-backed sliding window with in-memory fallback

### Database
- **PostgreSQL 16** (asyncpg driver)
- **Schema**: Users, roles, projects, expenses, vendors, categories, ledger, reconciliation, audit, notifications, processing jobs
- **Migrations**: Alembic with full history

### Cache & Queue
- **Redis 7**: Session cache, rate limiting, Celery broker/result backend
- **Key patterns**: Rate limit sliding windows, user token versions, JWT blacklists

### Object Storage
- **MinIO** (S3-compatible): Receipt files, evidence documents, audit exports
- **Buckets**: Evidence storage with presigned URLs (max 1-hour expiry enforced at API layer)

### Background Processing
- **Celery 5** with Redis broker/result backend
- **Workers**: OCR, LLM extraction, maintenance queues
- **Beat**: Persistent scheduler (daily retention, audit reports, budget alerts, cleanup, health checks)

### AI / LLM
- **Providers**: OpenAI (gpt-4o-mini), Google Gemini (gemini-1.5-flash), Anthropic (claude-3-haiku-20240307)
- **Extraction**: Structured JSON output with confidence scoring, fallback parsing
- **Config**: Provider selectable via `LLM_PROVIDER` env var

### OCR
- **Engine**: Tesseract (eng+hin) with OpenCV preprocessing
- **Pipeline**: Image -> deskew -> OCR -> text -> LLM extraction -> expense creation

### Authentication / Security
- **JWT**: HS256, 15-min access + 30-day refresh tokens
- **Rotation**: Refresh token family tracking with reuse detection -> family revocation
- **Revocation**: User token version mechanism (O(1) Redis INCR) for instant revoke-all
- **Logout**: Individual JTI blacklist with TTL from JWT exp claim
- **CORS**: Configurable origins via `CORS_ORIGINS` (no wildcard with credentials)
- **Security Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **SSRF Protection**: Webhook URL validation (blocks loopback, private RFC1918, metadata IPs)
- **Upload Security**: Extension allowlist, 25MB limit, 1MB chunked streaming, filename sanitization

## Project Structure

```
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/v1/         # API routes (auth, projects, expenses, vendors, categories, ledger, reconciliation, audit, notifications, OCR, extraction, webhooks, etc.)
│   │   ├── core/           # Config, security, database, logging, rate limiting, security headers
│   │   ├── models/         # SQLAlchemy models (users, projects, expenses, ledger, audit, etc.)
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── services/       # Business logic (auth, expense, posting, reconciliation, notification, etc.)
│   │   ├── repositories/   # Data access layer
│   │   ├── tasks/          # Celery tasks (OCR, LLM extraction, maintenance)
│   │   ├── integrations/   # External service adapters (WhatsApp, etc.)
│   │   ├── audit/          # Audit trail with correlation/causation chains
│   │   ├── reconciliation/ # Matching engine (reference/scored/manual)
│   │   ├── ledger/         # Double-entry posting service
│   │   ├── projects/       # Project domain
│   │   └── expenses/       # Expense domain
│   ├── alembic/            # Database migrations
│   ├── tests/              # Test suite (unit, integration, security, performance)
│   ├── pyproject.toml      # Python dependencies + tool config (ruff, mypy, pytest)
│   └── Dockerfile
├── frontend/               # React + TypeScript + Vite
│   ├── src/
│   │   ├── api/            # Generated API client + manual hooks
│   │   ├── components/     # Reusable UI components (Radix-based)
│   │   ├── pages/          # Page components (dashboard, expenses, projects, reconciliation, etc.)
│   │   └── hooks/          # Custom React hooks
│   ├── package.json
│   ├── Dockerfile          # Multi-stage: builder + nginx
│   └── nginx.conf          # Reverse proxy to backend API
├── android/                # Placeholder directory for planned mobile companion app
├── infrastructure/         # Docker Compose files
├── docs/                   # Documentation
│   ├── api/                # API documentation
│   ├── decisions/          # Architecture decision records
│   ├── API_DOCUMENTATION.md
│   ├── DEPLOYMENT_GUIDE.md
│   ├── MONITORING_DASHBOARD.json (Grafana)
│   └── RUNBOOKS.md
├── scripts/                # Utility scripts
├── .github/workflows/ci.yml # GitHub Actions CI (lint + test + docker builds)
├── .env.example            # Environment template (no real secrets)
├── .gitignore
└── README.md
```

## Prerequisites

- **Docker & Docker Compose** (v2+)
- **Node.js 20+** (for frontend development)
- **Python 3.12** (for backend development)
- **Git**

## Environment Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your configuration. **Never commit `.env`** — it contains secrets.

### Key Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `APP_ENV` | `development` \| `production` | Yes |
| `JWT_SECRET_KEY` | ≥32 chars, random secret | Yes (prod) |
| `DATABASE_URL` | PostgreSQL asyncpg URL | Yes |
| `REDIS_URL` | Redis connection URL | Yes |
| `MINIO_ENDPOINT` | MinIO host:port | Yes |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO credentials | Yes |
| `LLM_PROVIDER` | `openai` \| `gemini` \| `anthropic` | For extraction |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | Provider API keys | For extraction |
| `CORS_ORIGINS` | Comma-separated allowed origins | Yes |
| `SECURITY_HEADERS_HSTS_ENABLED` | `true` for HTTPS production | Prod only |

**Production**: The `Settings` validator rejects weak/default secrets (`change-me-in-production`, `<32 chars`) when `APP_ENV=production`.

**NEVER commit `.env`** — it is gitignored. Use `.env.example` as a template only.

## Docker Setup

### Core Services (Default Profile)
```bash
docker compose -f infrastructure/docker-compose.yml up -d
```
Services: PostgreSQL, Redis, MinIO, Backend, Worker, Beat

### With Frontend Container (Production Build)
```bash
docker compose -f infrastructure/docker-compose.yml --profile frontend up -d
```
Adds nginx-served frontend on port 5173.

### Service Ports (Host)
| Service | Port |
|---------|------|
| Backend API | 8001 |
| Frontend (dev) | 5173 |
| Frontend (Docker) | 5173 |
| PostgreSQL | 5433 |
| Redis | 6380 |
| MinIO API | 9002 |
| MinIO Console | 9003 |

### Health Checks
All services include Docker healthchecks. Backend health: `GET http://localhost:8001/api/v1/health`

## Local Development Setup

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Available at http://localhost:5173 (Vite dev server proxies /api to backend at http://localhost:8001)
```

### Generate API Client (after backend is running)
```bash
cd frontend
npm run generate:api
```

## Running Tests

### Backend
```bash
cd backend

# Install test dependencies
pip install -e .[dev]

# Targeted security/backend verification (runs without full DB)
# Priority 1: JWT type confusion, secret validation, IDOR, path traversal, SSRF, reviewer impersonation
pytest tests/verify_priority1_security.py -v

# Priority 2: Celery config, OCR-LLM linkage, expense updates, category persistence, commit ordering, WhatsApp auth, ledger flush order, double-entry, reconciliation queries
pytest tests/verify_priority2_backend.py -v

# Phase 2A security tests (token revocation, rotation, revoke-all, headers, CORS, Celery Beat)
pytest tests/test_phase2a_security_infra.py -v

# Full backend suite (requires PostgreSQL, Redis, MinIO)
# Windows host result: 166 passed, 2 failed (OCR tests requiring host Tesseract), 1 warning
pytest tests/ -v

# Run excluding OCR tests if Tesseract binary is not installed on host:
pytest tests/ --ignore=tests/test_ocr.py -v

# Linting & type checking
ruff check .
mypy app --ignore-missing-imports
```

### Frontend
```bash
cd frontend
npm run lint      # ESLint (135 warnings — technical debt; frontend build succeeds)
npm run build     # TypeScript + Vite build (success)
# No automated test runner configured
```

### Verification Status (Current)

| Test Suite | Status | Notes |
|------------|--------|-------|
| Priority 1 Security (7 tests) | ✅ 7 passed | JWT type confusion, secrets, IDOR, traversal, SSRF, impersonation |
| Priority 2 Backend (12 tests) | ✅ 12 passed | Celery, OCR-LLM, expenses, categories, commit order, WhatsApp, ledger, double-entry, reconciliation |
| Phase 2A Security/Infrastructure (25 tests) | ✅ 25 passed | Token revocation, rotation, revoke-all, headers, CORS, Celery Beat |
| Full Backend Suite (Windows Host) | ⚠️ 166 passed, 2 failed, 1 warning | 2 failed OCR tests require host Tesseract binary (not 100% passing on Windows) |
| Docker OCR Suite | ✅ 8 passed | Verified inside Docker backend environment with Tesseract installed |
| Frontend Lint | ⚠️ 135 warnings | Technical debt; frontend build succeeds |
| Frontend Tests | ❌ None | No automated test runner configured |

**Docker-specific verification**: Celery Beat deployment verified in compose file; worker/beat commands resolve to registered tasks. Docker OCR suite: 8 passed inside Docker backend environment with Tesseract installed.

**Host limitations**: Full integration tests require running PostgreSQL/Redis/MinIO. Full backend suite on Windows: 166 passed, 2 failed (OCR tests requiring host Tesseract binary), 1 warning.

## Security Hardening Implemented

- **JWT Type Separation**: Type claim validation (`type="access"` vs `type="refresh"`), preventing token type confusion; 15-min access + 30-day refresh
- **Refresh Token Rotation & Reuse Detection**: Token family tracking; detected reuse of a revoked token triggers revocation of the entire token family
- **Token Version Revoke-All**: User token version mechanism (O(1) Redis INCR) to instantly invalidate all active access tokens for a user
- **JTI Logout Blacklist**: Individual access token JTI blacklist in Redis with TTL matching remaining token lifetime from the `exp` claim
- **Configurable CORS**: Explicit allowed origins via `CORS_ORIGINS`, restricted methods and headers, no wildcard when credentials are supported
- **Security Headers**: Content Security Policy (CSP in dev/prod modes), HSTS (HTTPS only), X-Frame-Options (DENY), X-Content-Type-Options (nosniff), Referrer-Policy, Permissions-Policy
- **SSRF Protection**: Webhook URL validation blocking loopback (127.0.0.0/8), private RFC1918 ranges, link-local (169.254.0.0/16), reserved, multicast, and cloud metadata IPs
- **Upload Limits**: Extension allowlist, 25MB maximum size, 1MB chunked streaming, filename sanitization
- **IDOR Protection**: Presigned URL generation and evidence download enforce database record ownership checks
- **Reviewer Impersonation Prevention**: Staging review actions and reconciliation confirmation enforce `current_user.id` as reviewer/actor
- **Rate Limiting**: Redis-backed sliding window rate limiter (per-IP, per-route) with in-memory fallback
- **SQL Injection Prevention**: Database access uses SQLAlchemy ORM/parameterized queries.
- **Audit Trail Integrity**: Immutable events with correlation/causation chains and RESTRICT foreign keys on ledger entries## Current Verification Status

| Area | Status |
|------|--------|
| Backend core functionality (Windows) | ⚠️ 166 passed, 2 failed (OCR host Tesseract required), 1 warning |
| Docker OCR suite | ✅ 8 passed (inside Docker backend environment with Tesseract) |
| Security (Priority 1) | ✅ 7 passed |
| Backend Integrity (Priority 2) | ✅ 12 passed |
| Phase 2A Security/Infrastructure | ✅ 25 passed |
| Celery Beat deployment | ✅ Compose verified |
| JWT token security | ✅ Verified |
| Token revocation/rotation | ✅ Verified |
| Security headers/CORS | ✅ Verified |
| Docker Compose config | ✅ Validated |
| Double-entry ledger | ✅ Verified |
| Reconciliation engine | ✅ Verified |
| Frontend build | ✅ Success |
| Frontend tests | ❌ Not implemented |

## Known Limitations

1. **No frontend automated tests** — No test runner (Vitest/Playwright) configured
2. **No ledger reversal/void** — Posted entries are immutable; no compensating entry API
3. **Posting N+1 queries** — `list_postings`, `get_account_balances`, `get_trial_balance` need query optimization
4. **Prompt injection boundaries** — No input sanitization before LLM prompt construction
5. **LLM provider failover limitation** — Single provider at runtime; manual switch via env var
6. **Windows host Tesseract dependency** — 2 OCR tests require host Tesseract binary (8 OCR tests pass inside Docker backend environment)
7. **Frontend lint warnings** — 135 warnings (technical debt; frontend build succeeds)

## Roadmap / Future Work

- [ ] Frontend test suite (Vitest + Playwright)
- [ ] Ledger reversal/void with compensating entries
- [ ] Posting service query optimization (aggregated SQL)
- [ ] LLM provider failover with circuit breaker
- [ ] Prompt injection input sanitization
- [ ] Webhook retry/backoff observability
- [ ] Android companion app (Phase 14)
- [ ] Advanced reporting/analytics dashboards

## API Documentation

Local development URLs (when running via Docker or locally):
- **Swagger UI**: `http://localhost:8001/api/v1/docs`
- **ReDoc**: `http://localhost:8001/api/v1/redoc`
- **OpenAPI JSON**: `http://localhost:8001/api/v1/openapi.json`

### Key Endpoints

| Domain | Endpoints |
|--------|-----------|
| Auth | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/revoke-all`, `GET /auth/me` |
| Projects | `POST /projects`, `GET /projects`, `GET /projects/{project_id}` |
| Expenses | `POST /expenses`, `GET /expenses`, `GET /expenses/{expense_id}`, `PATCH /expenses/{expense_id}`, `POST /expenses/{expense_id}/transition` |
| Staging | `POST /staging/stage`, `GET /staging/expenses`, `POST /staging/expenses/{expense_id}/action` |
| Vendors | `POST /vendors`, `GET /vendors`, `GET /vendors/{vendor_id}` |
| Categories | `POST /categories`, `GET /categories` |
| Ledger | `POST /posting/post`, `GET /posting/expense/{expense_id}`, `GET /posting/`, `GET /posting/accounts/balances`, `GET /posting/trial-balance` |
| Reconciliation | `POST /reconciliation/match`, `POST /reconciliation/auto-match`, `GET /reconciliation/records`, `POST /reconciliation/records/{record_id}/action` |
| Evidence | `POST /evidence/upload`, `GET /evidence/{evidence_id}`, `POST /evidence/presigned-url` |
| OCR/Extraction | `POST /ocr/process`, `POST /extraction/process` |
| Notifications | `POST /notifications`, `GET /notifications`, `PATCH /notifications/preferences` |
| Webhooks | `GET /webhooks/whatsapp`, `POST /webhooks/whatsapp` |
| Audit & Compliance | `GET /audit/logs`, `GET /audit-compliance/reports`, `GET /audit-compliance/dashboard` |

## License

No license file present in this repository.
