"""
Production-ready Security module for Chronos Engine
Enhanced with rate limiting, secure key storage, and comprehensive audit logging
"""

import hashlib
import hmac
import secrets
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import threading
from collections import defaultdict, deque

from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, Index
from sqlalchemy.orm import declarative_base
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from src.core.models import Base


class SecurityError(Exception):
    """Security-related error"""
    pass


class RateLimitExceeded(SecurityError):
    """Rate limit exceeded error"""
    pass


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
    AUDIT_READ = "audit.read"
    SYSTEM_MONITOR = "system.monitor"


class SecurityLevel(Enum):
    """Security levels for different operations"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# Enhanced Database Models
class APIKeyDB(Base):
    """Database model for API keys with enhanced security"""
    __tablename__ = 'api_keys'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(128), nullable=False, unique=True, index=True)
    salt = Column(String(32), nullable=False)  # Salt for key hashing
    scopes_json = Column(Text, nullable=False)
    security_level = Column(String(20), default=SecurityLevel.MEDIUM.name)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)
    last_used_ip = Column(String(45), nullable=True)
    rate_limit_per_hour = Column(Integer, default=1000)

    # Enhanced indexes
    __table_args__ = (
        Index('idx_api_key_active_expires', 'active', 'expires_at'),
        Index('idx_api_key_security_level', 'security_level'),
    )


class AuditLogDB(Base):
    """Enhanced audit log with security context"""
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor = Column(String(100), nullable=False, index=True)
    actor_type = Column(String(20), default='api_key')  # api_key, user, system
    scope = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    action = Column(String(20), nullable=False)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True, index=True)
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(36), nullable=True, index=True)
    security_level = Column(String(20), default=SecurityLevel.MEDIUM.name)
    risk_score = Column(Integer, default=0)  # 0-100 risk assessment
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    # Enhanced indexes for security queries
    __table_args__ = (
        Index('idx_audit_entity', 'entity_type', 'entity_id'),
        Index('idx_audit_actor_scope', 'actor', 'scope'),
        Index('idx_audit_security_risk', 'security_level', 'risk_score'),
        Index('idx_audit_failure', 'success', 'timestamp'),
        Index('idx_audit_ip_time', 'ip_address', 'timestamp'),
    )


class SecurityIncidentDB(Base):
    """Security incidents tracking"""
    __tablename__ = 'security_incidents'

    id = Column(Integer, primary_key=True)
    incident_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    description = Column(Text, nullable=False)
    source_ip = Column(String(45), nullable=True, index=True)
    actor = Column(String(100), nullable=True, index=True)
    additional_context = Column(Text, nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)


# Domain Models
@dataclass
class APIKey:
    """Enhanced API key domain model"""
    id: Optional[int] = None
    name: str = ""
    key: Optional[str] = None  # Only available during creation
    scopes: Set[APIScope] = field(default_factory=set)
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    usage_count: int = 0
    active: bool = True
    created_by: Optional[str] = None
    last_used_ip: Optional[str] = None
    rate_limit_per_hour: int = 1000

    def to_db_model(self, key_hash: str, salt: str) -> APIKeyDB:
        """Convert to database model"""
        return APIKeyDB(
            id=self.id,
            name=self.name,
            key_hash=key_hash,
            salt=salt,
            scopes_json=json.dumps([scope.value for scope in self.scopes]),
            security_level=self.security_level.name,
            created_at=self.created_at,
            expires_at=self.expires_at,
            last_used_at=self.last_used_at,
            usage_count=self.usage_count,
            active=self.active,
            created_by=self.created_by,
            last_used_ip=self.last_used_ip,
            rate_limit_per_hour=self.rate_limit_per_hour
        )


@dataclass
class AuditEntry:
    """Enhanced audit log entry"""
    id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    actor: str = ""
    actor_type: str = "api_key"
    scope: str = ""
    entity_type: str = ""
    entity_id: str = ""
    action: str = ""
    old_values: Optional[Dict] = None
    new_values: Optional[Dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    risk_score: int = 0
    success: bool = True
    error_message: Optional[str] = None

    def to_db_model(self) -> AuditLogDB:
        """Convert to database model"""
        return AuditLogDB(
            id=self.id,
            timestamp=self.timestamp,
            actor=self.actor,
            actor_type=self.actor_type,
            scope=self.scope,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            action=self.action,
            old_values=json.dumps(self.old_values) if self.old_values else None,
            new_values=json.dumps(self.new_values) if self.new_values else None,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
            session_id=self.session_id,
            security_level=self.security_level.name,
            risk_score=self.risk_score,
            success=self.success,
            error_message=self.error_message
        )


class RateLimiter:
    """Thread-safe rate limiter"""

    def __init__(self):
        self._requests = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, identifier: str, limit: int, window_seconds: int = 3600) -> bool:
        """Check if request is allowed within rate limit"""
        with self._lock:
            now = time.time()
            window_start = now - window_seconds

            # Clean old requests
            request_times = self._requests[identifier]
            while request_times and request_times[0] < window_start:
                request_times.popleft()

            # Check limit
            if len(request_times) >= limit:
                return False

            # Add current request
            request_times.append(now)
            return True

    def get_usage(self, identifier: str, window_seconds: int = 3600) -> int:
        """Get current usage count for identifier"""
        with self._lock:
            now = time.time()
            window_start = now - window_seconds

            request_times = self._requests[identifier]
            # Count requests in current window
            return sum(1 for t in request_times if t >= window_start)


class SecureKeyStorage:
    """Secure storage for sensitive configuration"""

    def __init__(self, key_file: str = "data/master.key"):
        self.key_file = Path(key_file)
        self._key = None
        self._init_encryption()

    def _init_encryption(self):
        """Initialize encryption key"""
        try:
            if self.key_file.exists():
                with open(self.key_file, 'rb') as f:
                    self._key = f.read()
            else:
                # Generate new key
                self._key = Fernet.generate_key()
                # Ensure directory exists with secure permissions
                self.key_file.parent.mkdir(mode=0o700, exist_ok=True)
                with open(self.key_file, 'wb') as f:
                    f.write(self._key)
                # Set secure file permissions
                os.chmod(self.key_file, 0o600)

        except Exception as e:
            raise SecurityError(f"Failed to initialize encryption: {e}")

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data"""
        try:
            fernet = Fernet(self._key)
            encrypted = fernet.encrypt(data.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            raise SecurityError(f"Encryption failed: {e}")

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        try:
            fernet = Fernet(self._key)
            encrypted_bytes = base64.b64decode(encrypted_data.encode())
            decrypted = fernet.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            raise SecurityError(f"Decryption failed: {e}")


class SecurityService:
    """Enhanced security service with production features"""

    def __init__(self):
        self.signature_secret = self._get_or_create_signature_secret()
        self.rate_limiter = RateLimiter()
        self.key_storage = SecureKeyStorage()
        self._failed_attempts = defaultdict(list)
        self._lock = threading.Lock()

    def _get_or_create_signature_secret(self) -> str:
        """Get or create HMAC signature secret with secure storage"""
        secret_file = Path("data/signature_secret.key")

        # Ensure directory exists with secure permissions
        secret_file.parent.mkdir(mode=0o700, exist_ok=True)

        if secret_file.exists():
            # Verify file permissions
            stat_info = secret_file.stat()
            if stat_info.st_mode & 0o077:  # Check if group/other have permissions
                os.chmod(secret_file, 0o600)

            with open(secret_file, 'r') as f:
                return f.read().strip()
        else:
            secret = secrets.token_urlsafe(32)
            with open(secret_file, 'w') as f:
                f.write(secret)
            # Set secure permissions
            os.chmod(secret_file, 0o600)
            return secret

    def generate_api_key(self, security_level: SecurityLevel = SecurityLevel.MEDIUM) -> str:
        """Generate a secure API key based on security level"""
        if security_level == SecurityLevel.CRITICAL:
            # Longer key for critical operations
            return f"chronos_crit_{secrets.token_urlsafe(48)}"
        elif security_level == SecurityLevel.HIGH:
            return f"chronos_high_{secrets.token_urlsafe(40)}"
        else:
            return f"chronos_{secrets.token_urlsafe(32)}"

    def hash_api_key(self, api_key: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Hash API key with salt for secure storage"""
        if salt is None:
            salt = secrets.token_hex(16)

        # Use PBKDF2 for key stretching
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            iterations=100000,  # Industry standard
        )
        key_hash = base64.b64encode(kdf.derive(api_key.encode())).decode()
        return key_hash, salt

    def verify_api_key(self, api_key: str, stored_hash: str, salt: str) -> bool:
        """Verify API key against stored hash"""
        try:
            computed_hash, _ = self.hash_api_key(api_key, salt)
            return hmac.compare_digest(stored_hash, computed_hash)
        except Exception:
            return False

    def check_rate_limit(self, identifier: str, limit: int,
                        ip_address: Optional[str] = None) -> bool:
        """Check rate limit with additional IP-based limiting"""
        # Check primary identifier limit
        if not self.rate_limiter.is_allowed(identifier, limit):
            self._log_rate_limit_violation(identifier, ip_address)
            return False

        # Additional IP-based rate limiting for security
        if ip_address:
            ip_limit = limit * 5  # Allow 5x the normal rate per IP
            if not self.rate_limiter.is_allowed(f"ip:{ip_address}", ip_limit):
                self._log_rate_limit_violation(f"ip:{ip_address}", ip_address)
                return False

        return True

    def _log_rate_limit_violation(self, identifier: str, ip_address: Optional[str]):
        """Log rate limit violations for security monitoring"""
        with self._lock:
            now = time.time()
            self._failed_attempts[identifier].append(now)

            # Clean old attempts (last hour)
            cutoff = now - 3600
            self._failed_attempts[identifier] = [
                t for t in self._failed_attempts[identifier] if t >= cutoff
            ]

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
        """Verify HMAC signature with timestamp and replay protection"""
        try:
            # Check timestamp (prevent replay attacks)
            current_time = int(time.time())
            if abs(current_time - timestamp) > max_age:
                return False

            # Verify signature
            expected_signature = self.generate_signature(payload, timestamp)
            return hmac.compare_digest(signature, expected_signature)
        except Exception:
            return False

    def check_scopes(self, required_scopes: List[APIScope],
                    user_scopes: Set[APIScope]) -> bool:
        """Check if user has required scopes"""
        if APIScope.ADMIN in user_scopes:
            return True
        return all(scope in user_scopes for scope in required_scopes)

    def calculate_risk_score(self, action: str, ip_address: Optional[str],
                           user_agent: Optional[str], **context) -> int:
        """Calculate risk score for an action (0-100)"""
        risk_score = 0

        # High-risk actions
        high_risk_actions = ['delete', 'admin', 'backup', 'security']
        if any(action.lower().startswith(risk_action) for risk_action in high_risk_actions):
            risk_score += 30

        # IP-based risk assessment
        if ip_address:
            # Check for failed attempts from this IP
            failed_count = len(self._failed_attempts.get(f"ip:{ip_address}", []))
            risk_score += min(failed_count * 5, 20)

            # Check for private/local IPs (lower risk)
            if self._is_private_ip(ip_address):
                risk_score = max(0, risk_score - 10)

        # User agent risk
        if user_agent:
            suspicious_agents = ['curl', 'wget', 'python', 'bot']
            if any(agent in user_agent.lower() for agent in suspicious_agents):
                risk_score += 10

        # Time-based risk (off-hours access)
        current_hour = datetime.now().hour
        if current_hour < 6 or current_hour > 22:  # Outside business hours
            risk_score += 5

        return min(risk_score, 100)

    def _is_private_ip(self, ip_address: str) -> bool:
        """Check if IP address is private/local"""
        import ipaddress
        try:
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback
        except ValueError:
            return False


class AuditLogger:
    """Enhanced audit logging service with security features"""

    def __init__(self, db_session_factory, security_service: SecurityService):
        self.db_session_factory = db_session_factory
        self.security_service = security_service

    async def log_action(self, actor: str, scope: str, entity_type: str,
                        entity_id: str, action: str,
                        old_values: Optional[Dict] = None,
                        new_values: Optional[Dict] = None,
                        ip_address: Optional[str] = None,
                        user_agent: Optional[str] = None,
                        session_id: Optional[str] = None,
                        success: bool = True,
                        error_message: Optional[str] = None):
        """Enhanced audit logging with risk assessment"""

        # Calculate risk score
        risk_score = self.security_service.calculate_risk_score(
            action, ip_address, user_agent
        )

        # Determine security level
        security_level = SecurityLevel.LOW
        if risk_score > 70:
            security_level = SecurityLevel.CRITICAL
        elif risk_score > 50:
            security_level = SecurityLevel.HIGH
        elif risk_score > 25:
            security_level = SecurityLevel.MEDIUM

        entry = AuditEntry(
            actor=actor,
            scope=scope,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            security_level=security_level,
            risk_score=risk_score,
            success=success,
            error_message=error_message
        )

        try:
            async with self.db_session_factory() as session:
                session.add(entry.to_db_model())
                await session.commit()

                # Log security incidents for high-risk actions
                if risk_score > 80 or not success:
                    await self._log_security_incident(entry, session)

        except Exception as e:
            # Critical: audit logging must not fail
            import logging
            logging.getLogger(__name__).error(f"Audit logging failed: {e}")

    async def _log_security_incident(self, audit_entry: AuditEntry, session):
        """Log security incidents for monitoring"""
        incident_type = "failed_action" if not audit_entry.success else "high_risk_action"
        severity = "HIGH" if audit_entry.risk_score > 90 else "MEDIUM"

        description = (f"Security incident: {incident_type} by {audit_entry.actor} "
                      f"on {audit_entry.entity_type}:{audit_entry.entity_id} "
                      f"(risk score: {audit_entry.risk_score})")

        incident = SecurityIncidentDB(
            incident_type=incident_type,
            severity=severity,
            description=description,
            source_ip=audit_entry.ip_address,
            actor=audit_entry.actor,
            additional_context=json.dumps({
                "action": audit_entry.action,
                "risk_score": audit_entry.risk_score,
                "user_agent": audit_entry.user_agent
            })
        )

        session.add(incident)
        # No need to commit again, parent transaction will handle it


# Global instances
security_service = SecurityService()


from pathlib import Path  # Add missing import