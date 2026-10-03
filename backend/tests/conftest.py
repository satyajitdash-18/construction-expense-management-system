import os

os.environ["TESTING"] = "1"

import itertools  # noqa: E402 — must come after env setup

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from uuid import uuid4

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.enums import LifecycleStatus, PaymentMethod, ProjectStatus
from app.models.project import Project
from app.models.role import Role
from app.models.user import User
from app.services.auth import AuthService


# Use the container's internal database URL when running inside Docker
TEST_DATABASE_URL = settings.DATABASE_URL


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        from app.models.role import Role
        from sqlalchemy import select
        for r_name in ["admin", "project_manager", "site_user", "finance_user"]:
            existing = await session.execute(select(Role).where(Role.name == r_name))
            if not existing.scalar_one_or_none():
                session.add(Role(name=r_name))
        await session.commit()
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def override_db_dependency(db_session):
    async def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter():
    """Reset the in-memory rate limiter state before (and after) each test.

    The ``RateLimiter`` singleton keeps a sliding-window timestamp cache in
    memory when Redis is unavailable. Because all TestClient requests share
    the same loopback IP, the accumulated count bleeds across tests and causes
    spurious 429 responses for tests that run later in the session.

    This fixture calls ``rate_limiter.reset()`` — the same public method used
    by production management tooling — so the cache is empty at the start of
    every test.  Rate limiting logic itself is **not** disabled or modified.
    """
    from app.core.rate_limit import rate_limiter

    await rate_limiter.reset()
    yield
    await rate_limiter.reset()


@pytest_asyncio.fixture
async def async_client():
    try:
        from httpx import ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    except (ImportError, TypeError):
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user with project_manager role."""
    auth_service = AuthService(db_session)
    user = await auth_service.create_user(
        email=f"test_{uuid4()}@example.com",
        password="testpass123",
        full_name="Test User",
        role_names=["project_manager", "site_user", "finance_user"],
    )
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin_user(db_session):
    """Create a test admin user."""
    auth_service = AuthService(db_session)
    user = await auth_service.create_user(
        email=f"admin_{uuid4()}@example.com",
        password="adminpass123",
        full_name="Admin User",
        role_names=["admin"],
    )
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user):
    """Create auth headers for test user."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(test_admin_user):
    """Create auth headers for admin user."""
    token = create_access_token(data={"sub": str(test_admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_project(db_session, test_user):
    """Create a test project with unique code."""
    project = Project(
        name=f"Test Project {uuid4().hex[:8]}",
        code=f"TP-{uuid4().hex[:8]}",
        created_by=test_user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.refresh(project)
    return project