"""Unit-test conftest: override autouse DB/app fixtures from the root conftest.

Pure unit tests in this directory do not need a live database connection.
We stub the autouse fixtures from tests/conftest.py so that pytest does not
attempt to create an engine against the (unavailable) database host.

We also provide *explicit* `test_engine` and `db_session` fixtures so that
tests that declare them receive an in-memory fake rather than triggering a
real connection attempt.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class _FakeAsyncSession:
    """Minimal in-memory fake for AsyncSession.

    Supports the subset of the SQLAlchemy async session API used by the
    NotificationService (add, add_all, commit, get, refresh, execute, rollback).
    """

    def __init__(self) -> None:
        self._store: dict[tuple, object] = {}

    def add(self, obj: object) -> None:
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            try:
                setattr(obj, "id", uuid4())
            except Exception:
                pass
        pk = getattr(obj, "id", None) or id(obj)
        self._store[(type(obj), pk)] = obj

    def add_all(self, objs) -> None:
        for obj in objs:
            self.add(obj)

    async def commit(self) -> None:
        pass

    async def flush(self) -> None:
        for (_, pk), obj in list(self._store.items()):
            if not getattr(obj, "id", None):
                new_id = uuid4()
                try:
                    setattr(obj, "id", new_id)
                except Exception:
                    object.__setattr__(obj, "id", new_id)
                self._store[(type(obj), new_id)] = obj

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get(self, model, pk):  # noqa: ANN001
        return self._store.get((model, pk))

    async def refresh(self, obj: object, **kwargs) -> None:  # noqa: ANN003
        pass

    async def execute(self, statement):  # noqa: ANN001
        from app.models.role import Role
        from app.models.notification import Notification, NotificationPreference
        result = MagicMock()
        stmt_str = str(statement).lower()
        if "from roles" in stmt_str or "roles.name" in stmt_str:
            roles = [
                Role(id=uuid4(), name=name)
                for name in ["admin", "project_manager", "site_user", "finance_user"]
            ]
            result.scalars.return_value.all.return_value = roles
            result.scalar_one_or_none.return_value = None
        elif "notification_preferences" in stmt_str:
            prefs = [obj for obj in self._store.values() if isinstance(obj, NotificationPreference)]
            matching_pref = None
            params = {}
            try:
                params = statement.compile().params
            except Exception:
                pass
            target_event = params.get("event_type_1") or params.get("event_type")
            if target_event:
                for p in prefs:
                    if getattr(p, "event_type", None) == target_event:
                        matching_pref = p
                        break
            result.scalars.return_value.all.return_value = prefs
            result.scalars.return_value.first.return_value = matching_pref
            result.scalar_one_or_none.return_value = matching_pref
        elif "from notifications" in stmt_str:
            notifs = [obj for obj in self._store.values() if isinstance(obj, Notification)]
            result.scalars.return_value.all.return_value = notifs
            result.scalars.return_value.first.return_value = notifs[0] if notifs else None
            result.scalar_one_or_none.return_value = notifs[0] if notifs else None
        else:
            matching = list(self._store.values())
            result.scalars.return_value.all.return_value = matching
            result.scalars.return_value.first.return_value = matching[0] if matching else None
            result.scalar_one_or_none.return_value = matching[0] if matching else None
        return result

    # Context-manager support (used by some service code)
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest_asyncio.fixture(autouse=True)
async def override_db_dependency():
    """No-op: unit tests do not use the FastAPI dependency-injection layer."""
    yield


@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter():
    """No-op: unit tests do not exercise the rate-limiter middleware."""
    yield


@pytest_asyncio.fixture
async def test_engine():
    """Return a lightweight mock engine; unit tests have no real DB."""
    engine = MagicMock()
    engine.dispose = AsyncMock()
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):  # noqa: ARG001
    """Return an in-memory fake session.

    This allows unit tests to call service methods that add / get ORM objects
    without touching a real database.
    """
    yield _FakeAsyncSession()


