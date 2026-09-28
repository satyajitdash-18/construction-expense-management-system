# Implementation Plan

**Project:** AI-Assisted Construction Expense Management System
**Date:** 2026-09-20
**Phase:** 0 - Understand & Plan
**Status:** READY FOR PHASE 1

---

## 1. Restated Understanding

### Product Vision
Build an internal tool for a construction company staff (Project Managers, Site/Field Users, Finance Users, Administrators) to record construction-site payments in under 10 seconds per payment while maintaining complete, searchable, auditable financial records.

### Core Lifecycle (North Star)
Receipt Evidence (WhatsApp photo / SMS / Manual)
       |
       v
Source Event + Audit Event (same transaction, idempotent)
       |
       v
Async Pipeline: Media Download -> OCR -> LLM Extraction -> Confidence Scoring
       |
       +- High Confidence (>=0.75) --> STAGED
       |
       +- Low Confidence / Schema Invalid --> NEEDS_CONFIRMATION --> Human Review --> STAGED
       |
       v
Reconciliation: Payment Events (SMS/UPI) <-> Staged Expenses
       |
       +- Tier 1: Exact Reference Match --> MATCHED
       +- Tier 2: Scored (amount/date/vendor) --> MATCHED / AMBIGUOUS / UNMATCHED
       +- Tier 3: ML (deferred)
       |
       v
Ledger Posting: Double-entry (balanced debit/credit) --> Budget Updates
       |
       v
Complete Audit Trail: Every stage traceable to source evidence

### User Roles & Permissions
| Role | Capabilities |
|------|-------------|
| Administrator | Full system access, user management, integration config |
| Project Manager | Project CRUD, budgets, expenses for assigned projects, confirmations |
| Site/Field User | Submit expenses (WhatsApp/manual), view assigned projects |
| Finance User | Reconciliation queue, ledger posting, reports, audit history |

### Key Non-Negotiables (from Master Prompt)
1. Idempotency at DB constraint level - unique constraints on source_events(external_id) and idempotency_key
2. Audit-before-processing - audit event written in same transaction as source event
3. Async everything slow - OCR, LLM, media download in Celery workers
4. Never force a match - UNMATCHED/AMBIGUOUS are valid terminal states
5. Human gate on low confidence - LLM output never directly writes to DB
6. Provider-agnostic adapters - WhatsApp, OCR, LLM, Storage behind interfaces

---

## 2. Technology Stack Confirmation

| Layer | Technology | Decision Source |
|-------|-----------|-----------------|
| Language | Python 3.12+ | Master Prompt / Arch Report |
| API Framework | FastAPI | Master Prompt / Arch Report |
| Validation | Pydantic v2 | Master Prompt / Arch Report |
| ORM | SQLAlchemy 2.x (async) | Master Prompt / Arch Report |
| Migrations | Alembic | Master Prompt / Arch Report |
| Database | PostgreSQL 16+ | Master Prompt / Arch Report |
| Background Jobs | Celery + Redis | Master Prompt / Arch Report |
| OCR | Tesseract (MVP), PaddleOCR (production) | Master Prompt / Arch Report |
| LLM Extraction | Provider-agnostic interface (OpenAI/Gemini/Anthropic/Ollama) | Master Prompt / Arch Report |
| Object Storage | MinIO (S3-compatible) | Master Prompt / Arch Report |
| Ledger | Custom double-entry in PostgreSQL | User Decision / Arch Report |
| Frontend | React + TypeScript + Vite | Master Prompt / Arch Report |
| Frontend Data | TanStack Query | Master Prompt |
| Frontend Styling | Tailwind CSS | Master Prompt |
| API Client | Generated from OpenAPI (openapi-typescript) | Master Prompt |
| Android | Kotlin, native, sideloaded/enterprise | User Decision / Arch Report |
| Auth | Custom FastAPI JWT + RBAC | Master Prompt |
| Logging | structlog (JSON) | Master Prompt |
| Error Tracking | Sentry | Master Prompt |
| Metrics | prometheus-fastapi-instrumentator | Master Prompt |
| Containerization | Docker + Docker Compose | Master Prompt |
| Deployment (MVP) | Single VPS (Hetzner/DO) or Render | Master Prompt |
| CI/CD | GitHub Actions | Master Prompt |

Explicitly Excluded: Kubernetes, microservices, vector databases, Node/Java/Go/Rust/.NET on backend

---

## 3. Repository Structure (Confirmed)

project-root/
backend/
  app/
    api/v1/           # webhooks.py, expenses.py, projects.py, payments.py, reports.py, audit.py, auth.py
    core/             # config, security/JWT, DB session, logging, exceptions
    models/           # SQLAlchemy ORM models
    schemas/          # Pydantic request/response + LLM extraction schemas
    services/         # ExpenseService, ReconciliationService, LedgerService, AuditService, ProjectService, AuthService
    repositories/     # SQLAlchemy query layer (one per aggregate root)
    workers/          # Celery app + tasks (ocr, llm_extract, reconcile, media, notify)
    integrations/
      whatsapp/     # Cloud API client, webhook signature verification
      ocr/          # Tesseract/PaddleOCR adapters
      llm/          # LLMProvider ABC + concrete providers
      storage/      # MinIO/S3 client wrapper
      accounting/   # Firefly III export adapter (off by default)
    audit/            # audit event write helper
    reconciliation/   # matching engine, tiered rules
    ledger/           # double-entry posting logic
    projects/         # project/budget domain
    expenses/         # expense/lifecycle domain
  alembic/
  tests/
    unit/
    integration/
    golden_receipts/  # fixed OCR/LLM evaluation set
  pyproject.toml
  Dockerfile
frontend/
  src/
    api/              # generated OpenAPI client
    components/
    pages/
    hooks/
  package.json
  Dockerfile
android/
  app/                  # Kotlin companion (Phase 14)
infrastructure/
  docker-compose.yml
  docker-compose.prod.yml
docs/
  SRS.md                # copy of source SRS if provided
  decisions/            # one file per non-obvious decision
  api/                  # generated OpenAPI export
scripts/
.env.example
.gitignore
README.md

---

## 4. Database Schema (Confirmed)

### Core Tables (from Master Prompt DATABASE DESIGN)
- users, roles, user_roles
- projects, project_budgets
- vendors, expense_categories
- source_events (idempotency key + unique constraints)
- audit_events (append-only, DB-enforced via REVOKE)
- receipts (evidence artifacts with checksum)
- expenses (lifecycle_status enum: RECEIVED, VALIDATED, PROCESSING, EXTRACTED, NEEDS_CONFIRMATION, STAGED, RECONCILING, RECONCILED, POSTED, FAILED, REJECTED, UNMATCHED, AMBIGUOUS)
- expense_line_items
- payment_events (normalized SMS/UPI)
- reconciliation_records (MATCHED, UNMATCHED, AMBIGUOUS, MANUALLY_RESOLVED)
- ledger_accounts, ledger_entries (immutable, balanced pairs)
- processing_jobs, job_attempts
- integration_configs

### Critical Constraints
- source_events: UNIQUE on (source, external_id) + idempotency_key
- payment_events: UNIQUE on idempotency_key
- audit_events: REVOKE UPDATE, DELETE for app DB role
- ledger_entries: Application-level balanced-pair check + deferred constraint trigger (defense in depth)

### Indexing Strategy
- GIN on tsvector (expenses full-text search)
- pg_trgm GIN on vendors.name (fuzzy vendor matching)
- B-tree on all FKs, expenses.lifecycle_status, expenses.transaction_date, reconciliation_records.status

---

## 5. Ambiguities & Open Questions (Requiring Resolution)

| # | Question | Source | Priority | Target Resolution |
|---|----------|--------|----------|-------------------|
| 1 | Financial record retention period under Indian tax law | Master Prompt SECURITY / Arch Report 21 | HIGH | Phase 2 - consult CA/tax professional |
| 2 | GST e-invoicing turnover threshold (currently 5 crore?) | Arch Report 21 | HIGH | Phase 2 - verify current government notification |
| 3 | Android runtime permission model (OS-level vs Play Store policy) | Arch Report 11 | HIGH | Phase 2 - verify Android 14+ foreground service restrictions |
| 4 | Company-issued vs BYOD devices for Android companion | Arch Report 30.6 | MEDIUM | Phase 2 - business/HR decision |
| 5 | LLM provider pilot results (accuracy + cost per 100 receipts) | Master Prompt LLM PROVIDER ARCH / Arch Report 22 | HIGH | Phase 2/9 - run pilot before locking default |
| 6 | WhatsApp webhook response timeout (Meta current expectation) | Master Prompt NEEDS VERIFICATION | MEDIUM | Phase 11 - check Meta docs at implementation |
| 7 | WhatsApp mTLS/certificate trust store requirements | Master Prompt NEEDS VERIFICATION | MEDIUM | Phase 11 - check Meta docs at implementation |
| 8 | Hash-chained audit log (tamper evidence) | Master Prompt AUDIT SYSTEM / Arch Report 13 | LOW | Phase 13 - production hardening decision |
| 9 | Deployment target: VPS vs Render | Arch Report 20 / Master Prompt DEPLOYMENT | MEDIUM | Phase 1 - confirm solo developer Linux ops comfort |
| 10 | Ollama/local LLM as production fallback or dev-only? | Master Prompt LLM PROVIDER ARCH | LOW | Phase 9 - decide after pilot |

---

## 6. Implementation Phases (Master Prompt 17 Phases)

### Phase 0 - Understand & Plan - THIS DOCUMENT
- Read master prompt + architecture report
- Inspect repository (empty)
- Confirm tech stack with user decisions
- Produce docs/decisions/implementation-plan.md
- DoD: Plan file exists, internally consistent, user-approved

### Phase 1 - Repository & Dev Environment
- Repo structure per REPOSITORY STRUCTURE
- Docker Compose: backend + Postgres + Redis + MinIO (stubs)
- Alembic initialized
- /health endpoint with real DB connectivity check
- CI skeleton: lint (ruff) + test (pytest) on PR
- Base users, roles, user_roles tables + migration
- DoD: docker compose up succeeds; /health returns 200; one passing test in CI

### Phase 2 - Backend Foundation
- FastAPI app structure per REPOSITORY STRUCTURE
- JWT auth: login/refresh, argon2/bcrypt hashing
- RBAC dependency (role-gated routes)
- Structured logging (structlog + correlation_id)
- Error-handling middleware
- Sentry integration
- DoD: Login issues working JWT; protected route rejects invalid token; role-gated route rejects wrong role

### Phase 3 - Database & Migrations
- Full schema via Alembic migrations (all tables from section 4)
- Append-only audit_events permission REVOKE migration
- All unique/idempotency constraints
- DoD: Migrations run clean on fresh DB; UPDATE/DELETE on audit_events fails; duplicate-insert tests pass

### Phase 4 - Audit System
- AuditService with correlation/causation ID propagation
- Service-layer audit write helper (same transaction as entity write)
- Trivial entity write proving pattern end-to-end
- DoD: Test creates entity -> asserts exactly one audit event with correct entity_type/entity_id; traceable via causation_id

### Phase 5 - Projects & Budgets
- Full CRUD: ProjectService, ProjectRepository
- Budget vs. actual aggregate query (zero actuals initially)
- API endpoints: list/filter, create, detail, budget management
- Minimal frontend: project list + detail view
- DoD: API tests cover create/list/detail/budget-set; frontend lists/views project

### Phase 6 - Expense Domain (Manual Path Only)
- expenses/expense_line_items tables (migrated in Phase 3)
- ExpenseService state machine: all lifecycle states, legal-transition-checked
- Manual-entry API endpoint -> STAGED directly (no AI)
- DoD: Manual expense created, audited, visible in dashboard; illegal transition rejected with clear error

### Phase 7 - Object Storage & Evidence
- MinIO integration, StorageProvider interface
- Signed-URL generation, receipt upload endpoint (manual)
- Checksum (SHA256) recording on receipts
- DoD: Uploaded receipt stored, retrievable only via short-lived signed URL, checksum verifies

### Phase 8 - OCR
- Tesseract adapter behind OCRProvider interface
- Preprocessing pipeline: EXIF rotate, deskew, adaptive threshold, crop-to-bounds
- Celery ocr_task
- DoD: Real test receipt image produces OCR text via async task, recorded against expense

### Phase 9 - LLM Extraction
- LLMProvider interface + one concrete provider (pilot winner)
- ExpenseExtraction Pydantic schema (used for LLM structured output + internal validation)
- Confidence scoring: 3-signal combination (schema validity, OCR corroboration, provider confidence)
- Routing: >=threshold -> STAGED, <threshold or schema-invalid -> NEEDS_CONFIRMATION
- Run and record multi-provider pilot before locking default
- DoD: Real receipt -> validated, confidence-scored extraction; low-confidence case routes to NEEDS_CONFIRMATION; pilot results in docs/decisions/llm-provider-pilot.md

### Phase 10 - Confirmation Loop (Frontend + API)
- POST /expenses/{id}/confirm endpoint
- Pending Confirmations frontend screen: receipt image side-by-side with editable extracted fields
- Transition NEEDS_CONFIRMATION -> STAGED on confirm
- DoD: Human reviews/corrects NEEDS_CONFIRMATION expense -> STAGED, fully audited

### Phase 11 - WhatsApp Integration
- Webhook GET (verification handshake) + POST (HMAC-SHA256 verification)
- Media download task (immediate, before OCR/LLM)
- Idempotent source-event insert + enqueue
- Outbound WhatsApp confirmation/error replies
- Start Meta app/business verification in parallel (calendar time)
- DoD: Actual WhatsApp message with receipt photo -> NEEDS_CONFIRMATION/STAGED expense; duplicate webhook = exactly one result

### Phase 12 - Reconciliation Engine
- Tier 1: Deterministic reference match (UPI/bank ref) -> MATCHED (match_basis=reference)
- Tier 2: Scored weak-signal match (amount/date/vendor/project) -> MATCHED/AMBIGUOUS/UNMATCHED
- SELECT ... FOR UPDATE around match-and-post
- Reconciliation Queue frontend screen
- Exhaustive boundary-condition tests
- DoD: Deterministic match auto-resolves; ambiguous queues for Finance User; nothing auto-resolves on weak signal alone

### Phase 13 - Ledger & Budget Integration
- ledger_accounts, ledger_entries tables
- LedgerService posting logic: always-balanced double-entry (2 entries per posting)
- Project budget aggregate view reflects posted data
- DoD: Reconciled+confirmed expense posts 2 balanced ledger entries; budget view reflects it; double-post attempt rejected

### Phase 14 - Android SMS/UPI Companion
- Kotlin native app, foreground service with persistent notification
- On-device normalization (server-updatable regex/config table)
- Offline queue (Room DB) + idempotency key (client UUID)
- Device credential auth -> POST /api/v1/payments/events
- Confirm distribution-model assumption with project owner before writing code
- DoD: Real device captures test UPI SMS, queues offline, flushes idempotently; enters reconciliation like any payment event

### Phase 15 - Reporting & Dashboards
- Full dashboard: budget vs actual, category/vendor spend, processing-status breakdown
- Reports: by project/date/category/vendor/status
- Audit history viewer with visual causation_id trace-back
- DoD: Every number traces to persisted record; no client-side-only aggregation

### Phase 16 - Testing & Quality Gates
- Close coverage gaps across all phases
- Load-test webhook path under retry-storm conditions
- Full idempotency/reconciliation edge-case sweep
- Dependency vulnerability scan in CI (pip-audit, Dependabot)
- Golden-receipts evaluation (schema validity + field-level accuracy with tolerance)
- DoD: CI green on full run; no critical/high vulns; golden-receipts metric tracked

### Phase 17 - Security Hardening & Deployment
- Full security checklist (SECURITY section) executed
- Production deployment (VPS or Render)
- Prometheus/Grafana if warranted
- Backup/restore drill actually executed
- Retention policy confirmed with project owner (flag legal verification if unresolved)
- DoD: Real backup restored in test env; production reachable; full ingestion->confirm->reconcile->post smoke test passes

---

## 7. Key Decisions Recorded (to be created in docs/decisions/)

| Decision File | Status | Notes |
|---------------|--------|-------|
| ledger-approach.md | DECIDED | Custom double-entry in PostgreSQL (not Firefly III) |
| android-distribution.md | DECIDED | Sideload/enterprise on company-issued devices |
| llm-provider-pilot.md | PENDING | Run 100-receipt pilot before Phase 9 |
| retention-policy.md | OPEN | Requires CA/tax professional input |
| gst-einvoicing-threshold.md | OPEN | Verify current government notification |
| android-permission-model.md | OPEN | Verify Android 14+ runtime restrictions |
| deployment-target.md | PENDING | VPS vs Render - confirm in Phase 1 |
| whatsapp-webhook-timeout.md | OPEN | Check Meta docs at Phase 11 |
| audit-hash-chaining.md | DEFERRED | Phase 13 production hardening |
| ollama-role.md | DEFERRED | Decide after pilot |

---

## 8. Phase 1 Immediate Next Steps

1. Initialize repository with exact structure from section 3
2. Create docker-compose.yml with: backend (FastAPI), postgres, redis, minio
3. Create pyproject.toml with all backend dependencies
4. Initialize Alembic with first migration (users/roles/user_roles)
5. Create /health endpoint checking SELECT 1 on DB
6. Configure GitHub Actions for lint + test on PR
7. Add .env.example with all required variables documented
8. Verify docker compose up works end-to-end

---

## 9. Success Criteria for Phase 0 -> Phase 1 Transition

- Implementation plan documented and consistent with Master Prompt
- User decisions captured on all 4 key questions
- Open questions cataloged with owners and target phases
- Repository initialized with structure
- Docker Compose runs without errors
- /health returns 200 with DB connectivity
- CI pipeline executes on PR

---

Next Action: Proceed to Phase 1 - Repository & Dev Environment setup.
