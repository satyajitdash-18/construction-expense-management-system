import pytest
import pytest_asyncio
from uuid import UUID

from app.audit.helper import write_audit_event, write_audit_event_with_causation
from app.core.database import AsyncSessionLocal
from app.models.audit_event import AuditEvent


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_audit_event_creation(db_session):
    """Test creating a basic audit event."""
    from app.audit.helper import write_audit_event
    
    audit_id = await write_audit_event(
        session=db_session,
        event_type="test.created",
        entity_type="test_entity",
        entity_id=UUID("00000000-0000-0000-0000-000000000001"),
        actor_id=None,
        payload={"test": "data"},
    )
    
    assert audit_id is not None
    
    # Verify the audit event was created
    result = await db_session.get(AuditEvent, audit_id)
    assert result is not None
    assert result.event_type == "test.created"
    assert result.entity_type == "test_entity"
    assert result.payload == {"test": "data"}


@pytest.mark.asyncio
async def test_audit_causation_chain():
    """Test audit event causation chain - each write uses a fresh session."""
    from app.audit.helper import write_audit_event, write_audit_event_with_causation
    
    entity_id = UUID("00000000-0000-0000-0000-000000000002")
    correlation_id = UUID("00000000-0000-0000-0000-000000000003")
    
    # Create first audit event (source) - fresh session
    async with AsyncSessionLocal() as session1:
        first_audit_id = await write_audit_event(
            session=session1,
            event_type="source_event.received",
            entity_type="source_event",
            entity_id=entity_id,
            correlation_id=correlation_id,
            payload={"source": "whatsapp"},
        )
        await session1.commit()
    
    # Create second audit event caused by first - fresh session
    async with AsyncSessionLocal() as session2:
        second_audit_id = await write_audit_event_with_causation(
            session=session2,
            event_type="source_event.validated",
            entity_type="source_event",
            entity_id=entity_id,
            correlation_id=correlation_id,
            previous_audit_id=first_audit_id,
            payload={"validation": "passed"},
        )
        await session2.commit()
    
    # Create third audit event caused by second - fresh session
    async with AsyncSessionLocal() as session3:
        third_audit_id = await write_audit_event_with_causation(
            session=session3,
            event_type="expense.extracted",
            entity_type="expense",
            entity_id=entity_id,
            correlation_id=correlation_id,
            previous_audit_id=second_audit_id,
            payload={"confidence": 0.95},
        )
        await session3.commit()
    
    # Verify all three exist - fresh session
    async with AsyncSessionLocal() as session4:
        first = await session4.get(AuditEvent, first_audit_id)
        second = await session4.get(AuditEvent, second_audit_id)
        third = await session4.get(AuditEvent, third_audit_id)
        
        assert first is not None
        assert second is not None
        assert third is not None
        
        # Verify causation chain
        assert second.causation_id == first_audit_id
        assert third.causation_id == second_audit_id
        
        # Verify all share same correlation_id
        assert first.correlation_id == correlation_id
        assert second.correlation_id == correlation_id
        assert third.correlation_id == correlation_id
        
        # Verify payloads
        assert first.payload["source"] == "whatsapp"
        assert second.payload["validation"] == "passed"
        assert third.payload["confidence"] == 0.95