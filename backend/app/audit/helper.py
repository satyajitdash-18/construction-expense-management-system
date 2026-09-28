"""Audit event write helper for service layer.

This module provides the primary interface for services to write audit events
in the same transaction as the entity they describe. This ensures atomicity:
the entity and its audit trail are written together, or neither is.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import create_audit_service


async def write_audit_event(
    session: AsyncSession,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
) -> UUID:
    """
    Write an audit event in the same transaction as the calling service.

    This is the primary helper for service-layer audit writes. It creates
    an AuditService and records the event in the same session/transaction
    as the entity operation.

    Args:
        session: The async database session (same as entity operation)
        event_type: Type of event (e.g., "expense.created", "project.updated")
        entity_type: Type of entity (e.g., "expense", "project", "vendor")
        entity_id: ID of the entity being operated on
        actor_id: ID of the user who triggered the action, or None for system
        payload: Additional event data
        correlation_id: Correlation ID for the flow (auto from context if None)
        causation_id: ID of the audit event that caused this one

    Returns:
        The ID of the created audit event, for use as causation_id in next step
    """
    audit_service = create_audit_service(session)
    audit_event = await audit_service.record(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        payload=payload,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return audit_event.id


async def write_audit_event_with_causation(
    session: AsyncSession,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    correlation_id: UUID | None = None,
    previous_audit_id: UUID | None = None,
) -> UUID:
    """
    Write an audit event with explicit causation to a previous audit event.

    This is the primary method for chaining audit events in a flow.

    Args:
        session: The async database session
        event_type: Type of event
        entity_type: Type of entity
        entity_id: ID of the entity
        actor_id: ID of the actor (user) or None
        payload: Additional event data
        correlation_id: Correlation ID (auto from context if None)
        previous_audit_id: ID of the audit event that caused this one

    Returns:
        The ID of the created audit event
    """
    audit_service = create_audit_service(session)
    audit_event = await audit_service.record_with_causation(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        payload=payload,
        correlation_id=correlation_id,
        previous_audit_id=previous_audit_id,
    )
    return audit_event.id
