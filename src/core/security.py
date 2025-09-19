"""
Security module for Chronos Engine - API Keys, HMAC, and Audit Log
Implements the security foundation without overengineering
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import json

from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, Index
from sqlalchemy.orm import declarative_base

from src.core.models import Base


class APIScope(Enum):
    """API permission scopes"""
    EVENTS_READ = "events.read"
    EVENTS_WRITE = "events.write"
    COMMANDS_MANAGE = "commands.manage"
    ADMIN = "admin"
    TEMPLATES_READ = "templates.read"
    TEMPLATES_WRITE = "templates.write"
    WHITELISTS_MANAGE = "whitelists.manage"
    WORKFLOWS_MANAGE = "workflows.manage"
    BACKUPS_MANAGE = "backups.manage"
    INTEGRATIONS_MANAGE = "integrations.manage"


# Database Models
class APIKeyDB(Base):
    """Database model for API keys"""
    __tablename__ = 'api_keys'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(128), nullable=False, unique=True, index=True)
    scopes_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)


class AuditLogDB(Base):
    """Database model for audit log - immutable"""
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor = Column(String(100), nullable=False, index=True)
    scope = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    action = Column(String(20), nullable=False)  # create, update, delete
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Index for common queries
    __table_args__ = (
        Index('idx_audit_entity', 'entity_type', 'entity_id'),
        Index('idx_audit_actor_scope', 'actor', 'scope'),
    )


# Domain Models
@dataclass
class APIKey:
    """API key domain model"""
    id: Optional[int] = None
    name: str = ""
    key: Optional[str] = None  # Only available during creation
    scopes: Set[APIScope] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    active: bool = True
    created_by: Optional[str] = None

    def to_db_model(self, key_hash: str) -> APIKeyDB:
        """Convert to database model"""
        return APIKeyDB(
            id=self.id,
            name=self.name,
            key_hash=key_hash,
            scopes_json=json.dumps([scope.value for scope in self.scopes]),
            created_at=self.created_at,
            expires_at=self.expires_at,
            last_used_at=self.last_used_at,
            active=self.active,
            created_by=self.created_by
        )


@dataclass
class AuditEntry:
    """Audit log entry domain model"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    actor: str = ""
    scope: str = ""
    entity_type: str = ""
    entity_id: str = ""
    action: str = ""
    old_values: Optional[Dict] = None
    new_values: Optional[Dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_db_model(self) -> AuditLogDB:
        """Convert to database model"""
        return AuditLogDB(
            id=self.id,
            timestamp=self.timestamp,
            actor=self.actor,
            scope=self.scope,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            action=self.action,
            old_values=json.dumps(self.old_values) if self.old_values else None,
            new_values=json.dumps(self.new_values) if self.new_values else None,
            ip_address=self.ip_address,
            user_agent=self.user_agent
        )


class SecurityService:
    """Security service for API keys, authentication, and audit logging"""

    def __init__(self):
        self.signature_secret = self._get_or_create_signature_secret()

    def _get_or_create_signature_secret(self) -> str:
        """Get or create HMAC signature secret"""
        # In production, this should be stored securely (env var, config file)
        # For now, we'll use a fixed secret that persists across restarts
        import os
        secret_file = "data/signature_secret.key"

        os.makedirs("data", exist_ok=True)

        if os.path.exists(secret_file):
            with open(secret_file, 'r') as f:
                return f.read().strip()
        else:
            secret = secrets.token_urlsafe(32)
            with open(secret_file, 'w') as f:
                f.write(secret)
            return secret

    def generate_api_key(self) -> str:
        """Generate a secure API key"""
        return f"chronos_{secrets.token_urlsafe(32)}"

    def hash_api_key(self, api_key: str) -> str:
        """Hash API key for secure storage"""
        return hashlib.sha256(api_key.encode()).hexdigest()

    def verify_api_key_format(self, api_key: str) -> bool:
        """Verify API key format"""
        return api_key.startswith("chronos_") and len(api_key) > 15

    def create_api_key(self, name: str, scopes: List[str],
                      expires_in_days: Optional[int] = None,
                      created_by: Optional[str] = None) -> APIKey:
        """Create a new API key"""
        key = self.generate_api_key()
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        # Convert string scopes to enum
        scope_enums = set()
        for scope_str in scopes:
            try:
                scope_enums.add(APIScope(scope_str))
            except ValueError:
                raise ValueError(f"Invalid scope: {scope_str}")

        api_key = APIKey(
            name=name,
            key=key,
            scopes=scope_enums,
            expires_at=expires_at,
            created_by=created_by
        )

        return api_key

    def generate_signature(self, payload: str, timestamp: int) -> str:
        """Generate HMAC signature for webhook/API requests"""
        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            self.signature_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    def verify_signature(self, payload: str, signature: str,
                        timestamp: int, max_age: int = 300) -> bool:
        """Verify HMAC signature with timestamp check"""
        # Check timestamp (prevent replay attacks)
        current_time = int(time.time())
        if abs(current_time - timestamp) > max_age:
            return False

        # Verify signature
        expected_signature = self.generate_signature(payload, timestamp)
        return hmac.compare_digest(signature, expected_signature)

    def check_scopes(self, required_scopes: List[APIScope],
                    user_scopes: Set[APIScope]) -> bool:
        """Check if user has required scopes"""
        if APIScope.ADMIN in user_scopes:
            return True
        return all(scope in user_scopes for scope in required_scopes)


class AuditLogger:
    """Audit logging service"""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    async def log_action(self, actor: str, scope: str, entity_type: str,
                        entity_id: str, action: str,
                        old_values: Optional[Dict] = None,
                        new_values: Optional[Dict] = None,
                        ip_address: Optional[str] = None,
                        user_agent: Optional[str] = None):
        """Log an action to audit log"""
        entry = AuditEntry(
            actor=actor,
            scope=scope,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent
        )

        async with self.db_session_factory() as session:
            session.add(entry.to_db_model())
            await session.commit()

    async def get_audit_log(self, entity_type: Optional[str] = None,
                           entity_id: Optional[str] = None,
                           actor: Optional[str] = None,
                           limit: int = 100) -> List[AuditEntry]:
        """Get audit log entries with optional filtering"""
        from sqlalchemy import select

        async with self.db_session_factory() as session:
            query = select(AuditLogDB).order_by(AuditLogDB.timestamp.desc())

            if entity_type:
                query = query.where(AuditLogDB.entity_type == entity_type)
            if entity_id:
                query = query.where(AuditLogDB.entity_id == entity_id)
            if actor:
                query = query.where(AuditLogDB.actor == actor)

            query = query.limit(limit)

            result = await session.execute(query)
            db_entries = result.scalars().all()

            return [self._db_to_domain(entry) for entry in db_entries]

    def _db_to_domain(self, db_entry: AuditLogDB) -> AuditEntry:
        """Convert database model to domain model"""
        return AuditEntry(
            id=db_entry.id,
            timestamp=db_entry.timestamp,
            actor=db_entry.actor,
            scope=db_entry.scope,
            entity_type=db_entry.entity_type,
            entity_id=db_entry.entity_id,
            action=db_entry.action,
            old_values=json.loads(db_entry.old_values) if db_entry.old_values else None,
            new_values=json.loads(db_entry.new_values) if db_entry.new_values else None,
            ip_address=db_entry.ip_address,
            user_agent=db_entry.user_agent
        )


# Global security service instance
security_service = SecurityService()