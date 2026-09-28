from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_correlation_id, get_logger, set_correlation_id
from app.models.audit_event import AuditEvent

logger = get_logger(__name__)


class AuditService:
    """Service for writing audit events with correlation/causation ID tracking."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        actor_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
    ) -> AuditEvent:
        """
        Record an audit event with full correlation/causation chain.

        Args:
            event_type: Type of event (e.g., "expense.created", "expense.confirmed")
            entity_type: Type of entity (e.g., "expense", "project", "vendor")
            entity_id: ID of the entity
            actor_id: ID of the actor (user) who triggered the event, or None for system
            payload: Additional event data
            correlation_id: ID tying together all events in one flow (auto-generated if None)
            causation_id: ID of the audit event that caused this one (chained automatically)

        Returns:
            The created AuditEvent
        """
        # Use provided correlation_id or get from context
        if correlation_id is None:
            correlation_id = UUID(get_correlation_id())

        # Create audit event with client-side UUID so it is available before flush
        audit_event = AuditEvent(
            id=uuid4(),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload or {},
        )

        self.session.add(audit_event)
        await self.session.flush()

        return audit_event

    async def record_with_causation(
        self,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        actor_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
        previous_audit_id: UUID | None = None,
    ) -> AuditEvent:
        """
        Record an audit event with explicit causation to a previous audit event.

        This is the primary method for chaining audit events in a flow.
        """
        return await self.record(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=previous_audit_id,
        )


@contextmanager
def audit_context(correlation_id: UUID | None = None) -> Generator[UUID | None, None, None]:
    """Context manager for setting correlation ID for the duration of a flow."""
    previous_id = get_correlation_id()
    new_id = set_correlation_id(str(correlation_id) if correlation_id else None)
    try:
        yield UUID(new_id) if new_id else None
    finally:
        if previous_id:
            set_correlation_id(previous_id)
        else:
            # Clear if there was no previous
            pass


def create_audit_service(session: AsyncSession) -> AuditService:
    """Factory for creating AuditService with a session."""
    return AuditService(session)
