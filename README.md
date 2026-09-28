# Construction Expense Management System

AI-Assisted Construction Expense Management System - Phase 1: Repository & Dev Environment

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.12 (for backend development)

### Development Setup

1. **Copy environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Start core services (PostgreSQL, Redis, MinIO, Backend, Worker):**
   ```bash
   docker compose -f infrastructure/docker-compose.yml up -d
   ```

3. **Verify backend health:**
   ```bash
   curl http://localhost:8000/health
   # Expected: {"status":"ok","db":"connected","version":"0.1.0","env":"development"}
   ```

4. **Start frontend development server (separate terminal):**
   ```bash
   cd frontend
   npm install
   npm run dev
   # Frontend available at http://localhost:5173
   ```

5. **Run tests:**
   ```bash
   cd backend
   pip install -e .[dev]
   pytest tests -v
   ```

### Docker Compose Profiles

- **Core services (default):** `docker compose -f infrastructure/docker-compose.yml up -d`
  - postgres, redis, minio, backend, worker
- **With frontend container:** `docker compose -f infrastructure/docker-compose.yml --profile frontend up -d`
  - Includes nginx-served production frontend build

### Project Structure

```
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/v1/         # API routes (health, auth)
│   │   ├── core/           # Config, security, database, logging
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   ├── repositories/   # Data access layer
│   │   ├── workers/        # Celery tasks
│   │   ├── integrations/   # External service adapters
│   │   ├── audit/          # Audit trail
│   │   ├── reconciliation/ # Matching engine
│   │   ├── ledger/         # Double-entry ledger
│   │   ├── projects/       # Project domain
│   │   └── expenses/       # Expense domain
│   ├── alembic/            # Database migrations
│   ├── tests/              # Test suite
│   ├── pyproject.toml      # Python dependencies
│   └── Dockerfile
├── frontend/               # React + TypeScript + Vite
│   ├── src/
│   │   ├── api/            # Generated API client
│   │   ├── components/     # React components
│   │   ├── pages/          # Page components
│   │   └── hooks/          # Custom hooks
│   ├── package.json
│   ├── Dockerfile          # Production build
│   └── nginx.conf
├── android/                # Kotlin companion app (Phase 14)
├── infrastructure/         # Docker Compose files
├── docs/                   # Documentation & decisions
└── scripts/                # Utility scripts
```

### API Documentation

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json

### Health Check

```bash
curl http://localhost:8000/health
```

### Database Migrations

```bash
cd backend
alembic upgrade head          # Apply migrations
alembic revision --autogenerate -m "description"  # Create new migration
alembic downgrade -1          # Rollback one migration
```

### Environment Variables

See `.env.example` for all configurable options.

### Phase 1 Status

- ✅ Repository structure
- ✅ Docker Compose with healthchecks
- ✅ Alembic initialized with users/roles migration
- ✅ /health endpoint with real DB connectivity check
- ✅ CI pipeline (lint + test)
- ✅ Base tables: users, roles, user_roles