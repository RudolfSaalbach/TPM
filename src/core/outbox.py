"""
Outbox pattern implementation for reliable external integrations
Ensures no duplicate sends and proper retry handling
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, Index
from sqlalchemy.orm import declarative_base

from src.core.models import Base


class OutboxStatus(Enum):
    """Outbox entry status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class OutboxEntryDB(Base):
    """Database model for outbox entries"""
    __tablename__ = 'outbox'

    id = Column(Integer, primary_key=True, index=True)
    idempotency_key = Column(String(36), unique=True, nullable=False, index=True)
    target_system = Column(String(100), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    headers = Column(Text, nullable=True)  # JSON
    status = Column(String(20), nullable=False, default=OutboxStatus.PENDING.value, index=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    timeout_seconds = Column(Integer, default=30)

    # Index for processing queries
    __table_args__ = (
        Index('idx_outbox_processing', 'status', 'next_retry_at'),
    )


@dataclass
class OutboxEntry:
    """Outbox entry domain model"""
    id: Optional[int] = None
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_system: str = ""
    event_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    timeout_seconds: int = 30

    def to_db_model(self) -> OutboxEntryDB:
        """Convert to database model"""
        return OutboxEntryDB(
            id=self.id,
            idempotency_key=self.idempotency_key,
            target_system=self.target_system,
            event_type=self.event_type,
            payload=json.dumps(self.payload),
            headers=json.dumps(self.headers),
            status=self.status.value,
            retry_count=self.retry_count,
            max_retries=self.max_retries,
            next_retry_at=self.next_retry_at,
            created_at=self.created_at,
            processed_at=self.processed_at,
            completed_at=self.completed_at,
            last_error=self.last_error,
            timeout_seconds=self.timeout_seconds
        )


class OutboxService:
    """Service for managing outbox entries and processing"""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self._processing = False

    async def add_entry(self, target_system: str, event_type: str,
                       payload: Dict[str, Any], headers: Dict[str, str] = None,
                       idempotency_key: Optional[str] = None,
                       max_retries: int = 3, timeout_seconds: int = 30) -> str:
        """Add entry to outbox with idempotency"""
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())

        entry = OutboxEntry(
            idempotency_key=idempotency_key,
            target_system=target_system,
            event_type=event_type,
            payload=payload,
            headers=headers or {},
            max_retries=max_retries,
            timeout_seconds=timeout_seconds
        )

        async with self.db_session_factory() as session:
            # Check if entry already exists (idempotency)
            from sqlalchemy import select
            existing = await session.execute(
                select(OutboxEntryDB).where(
                    OutboxEntryDB.idempotency_key == idempotency_key
                )
            )
            if existing.scalar_one_or_none():
                return idempotency_key

            # Add new entry
            session.add(entry.to_db_model())
            await session.commit()

        return idempotency_key

    async def get_pending_entries(self, limit: int = 100) -> List[OutboxEntry]:
        """Get pending entries ready for processing"""
        from sqlalchemy import select, or_

        async with self.db_session_factory() as session:
            query = select(OutboxEntryDB).where(
                or_(
                    OutboxEntryDB.status == OutboxStatus.PENDING.value,
                    (OutboxEntryDB.status == OutboxStatus.FAILED.value) &
                    (OutboxEntryDB.next_retry_at <= datetime.utcnow()) &
                    (OutboxEntryDB.retry_count < OutboxEntryDB.max_retries)
                )
            ).order_by(OutboxEntryDB.created_at).limit(limit)

            result = await session.execute(query)
            db_entries = result.scalars().all()

            return [self._db_to_domain(entry) for entry in db_entries]

    async def mark_processing(self, entry_id: int) -> bool:
        """Mark entry as processing"""
        from sqlalchemy import select

        async with self.db_session_factory() as session:
            entry = await session.get(OutboxEntryDB, entry_id)
            if not entry or entry.status not in [OutboxStatus.PENDING.value, OutboxStatus.FAILED.value]:
                return False

            entry.status = OutboxStatus.PROCESSING.value
            entry.processed_at = datetime.utcnow()
            await session.commit()
            return True

    async def mark_completed(self, entry_id: int):
        """Mark entry as completed"""
        async with self.db_session_factory() as session:
            entry = await session.get(OutboxEntryDB, entry_id)
            if entry:
                entry.status = OutboxStatus.COMPLETED.value
                entry.completed_at = datetime.utcnow()
                await session.commit()

    async def mark_failed(self, entry_id: int, error: str):
        """Mark entry as failed and schedule retry"""
        async with self.db_session_factory() as session:
            entry = await session.get(OutboxEntryDB, entry_id)
            if not entry:
                return

            entry.retry_count += 1
            entry.last_error = error

            if entry.retry_count >= entry.max_retries:
                entry.status = OutboxStatus.DEAD_LETTER.value
            else:
                entry.status = OutboxStatus.FAILED.value
                # Exponential backoff: 2^retry_count minutes
                backoff_minutes = 2 ** entry.retry_count
                entry.next_retry_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)

            await session.commit()

    async def get_dead_letter_queue(self, limit: int = 100) -> List[OutboxEntry]:
        """Get dead letter queue entries"""
        from sqlalchemy import select

        async with self.db_session_factory() as session:
            query = select(OutboxEntryDB).where(
                OutboxEntryDB.status == OutboxStatus.DEAD_LETTER.value
            ).order_by(OutboxEntryDB.created_at.desc()).limit(limit)

            result = await session.execute(query)
            db_entries = result.scalars().all()

            return [self._db_to_domain(entry) for entry in db_entries]

    async def retry_entry(self, entry_id: int) -> bool:
        """Manually retry a failed or dead letter entry"""
        async with self.db_session_factory() as session:
            entry = await session.get(OutboxEntryDB, entry_id)
            if not entry:
                return False

            entry.status = OutboxStatus.PENDING.value
            entry.next_retry_at = None
            entry.last_error = None
            await session.commit()
            return True

    async def cleanup_old_entries(self, days_old: int = 30):
        """Clean up old completed entries"""
        from sqlalchemy import delete

        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        async with self.db_session_factory() as session:
            await session.execute(
                delete(OutboxEntryDB).where(
                    (OutboxEntryDB.status == OutboxStatus.COMPLETED.value) &
                    (OutboxEntryDB.completed_at < cutoff_date)
                )
            )
            await session.commit()

    def _db_to_domain(self, db_entry: OutboxEntryDB) -> OutboxEntry:
        """Convert database model to domain model"""
        return OutboxEntry(
            id=db_entry.id,
            idempotency_key=db_entry.idempotency_key,
            target_system=db_entry.target_system,
            event_type=db_entry.event_type,
            payload=json.loads(db_entry.payload),
            headers=json.loads(db_entry.headers) if db_entry.headers else {},
            status=OutboxStatus(db_entry.status),
            retry_count=db_entry.retry_count,
            max_retries=db_entry.max_retries,
            next_retry_at=db_entry.next_retry_at,
            created_at=db_entry.created_at,
            processed_at=db_entry.processed_at,
            completed_at=db_entry.completed_at,
            last_error=db_entry.last_error,
            timeout_seconds=db_entry.timeout_seconds
        )

    async def start_processor(self, interval_seconds: int = 30):
        """Start the outbox processor background task"""
        if self._processing:
            return

        self._processing = True

        async def process_loop():
            while self._processing:
                try:
                    await self._process_batch()
                except Exception as e:
                    # Log error but continue processing
                    print(f"Outbox processing error: {e}")

                await asyncio.sleep(interval_seconds)

        # Start background task
        asyncio.create_task(process_loop())

    async def stop_processor(self):
        """Stop the outbox processor"""
        self._processing = False

    async def _process_batch(self):
        """Process a batch of pending entries"""
        entries = await self.get_pending_entries(limit=10)

        for entry in entries:
            if await self.mark_processing(entry.id):
                # Process entry with registered handler
                try:
                    success = await self._handle_entry(entry)
                    if success:
                        await self.mark_completed(entry.id)
                    else:
                        await self.mark_failed(entry.id, "Handler returned false")
                except Exception as e:
                    await self.mark_failed(entry.id, str(e))

    async def _handle_entry(self, entry: OutboxEntry) -> bool:
        """Handle individual outbox entry - to be overridden by specific implementations"""
        # This would be implemented by specific integration handlers
        # For now, just return success
        return True


# Service registry for different target systems
class OutboxHandlerRegistry:
    """Registry for outbox handlers per target system"""

    def __init__(self):
        self._handlers = {}

    def register_handler(self, target_system: str, handler):
        """Register a handler for a target system"""
        self._handlers[target_system] = handler

    async def handle_entry(self, entry: OutboxEntry) -> bool:
        """Route entry to appropriate handler"""
        handler = self._handlers.get(entry.target_system)
        if not handler:
            raise ValueError(f"No handler registered for system: {entry.target_system}")

        return await handler(entry)


# Global registry instance
outbox_registry = OutboxHandlerRegistry()