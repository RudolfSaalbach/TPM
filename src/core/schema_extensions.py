"""
Schema extensions for the new architecture
Adds the new tables required for the enhanced security and integration features
"""

from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, JSON, Index
from src.core.models import Base


# Note: WhitelistDB is defined in models.py to avoid duplication

# Note: WorkflowDB and EmailTemplateDB are defined in models.py to avoid duplication

class WebhookTemplateDB(Base):
    """Database model for webhook payload templates"""
    __tablename__ = 'webhook_templates'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    target_system = Column(String(100), nullable=False, index=True)
    payload_template = Column(Text, nullable=False)  # JSON template with placeholders
    headers_template = Column(JSON, nullable=True)  # Headers with placeholders
    variables = Column(JSON, nullable=True)  # List of available variables
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow(),
                      onupdate=lambda: __import__('datetime').datetime.utcnow())
    created_by = Column(String(100), nullable=True)


# Email Service Tables
class EmailLogDB(Base):
    """Database model for email sending logs"""
    __tablename__ = 'email_logs'

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(200), nullable=True, index=True)
    recipient = Column(String(255), nullable=False, index=True)
    subject = Column(String(500), nullable=False)
    template_id = Column(Integer, nullable=True, index=True)
    status = Column(String(50), default='sent', index=True)  # sent, failed, bounced
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)


# Backup Management Tables
class BackupJobDB(Base):
    """Database model for backup jobs and schedules"""
    __tablename__ = 'backup_jobs'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    schedule_cron = Column(String(100), nullable=True)  # Cron expression for scheduled backups
    backup_type = Column(String(50), default='full')  # full, incremental
    include_files = Column(JSON, nullable=True)  # Files/patterns to include
    exclude_files = Column(JSON, nullable=True)  # Files/patterns to exclude
    retention_days = Column(Integer, default=30)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow(),
                      onupdate=lambda: __import__('datetime').datetime.utcnow())
    created_by = Column(String(100), nullable=True)


class BackupHistoryDB(Base):
    """Database model for backup execution history"""
    __tablename__ = 'backup_history'

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, nullable=True, index=True)  # NULL for manual backups
    backup_filename = Column(String(500), nullable=False)
    backup_size_bytes = Column(Integer, nullable=True)
    backup_type = Column(String(50), default='manual')
    status = Column(String(50), default='completed', index=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())
    completed_at = Column(DateTime, nullable=True)
    checksum = Column(String(128), nullable=True)  # SHA256 checksum


# Event Mode Management
class EventModeDB(Base):
    """Database model for event scheduling modes"""
    __tablename__ = 'event_modes'

    event_id = Column(String(36), primary_key=True, index=True)
    mode = Column(String(20), default='free', index=True)  # 'free' or 'auto_plan'
    auto_reschedule = Column(Boolean, default=False)
    conflict_resolution = Column(String(50), default='suggest')  # suggest, reschedule, ignore
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow(),
                      onupdate=lambda: __import__('datetime').datetime.utcnow())


# Integration Configuration Tables
class IntegrationConfigDB(Base):
    """Database model for integration configurations"""
    __tablename__ = 'integration_configs'

    id = Column(Integer, primary_key=True, index=True)
    system_name = Column(String(100), nullable=False, unique=True, index=True)
    config_data = Column(JSON, nullable=False)  # System-specific configuration
    webhook_url = Column(String(500), nullable=True)
    webhook_secret = Column(String(128), nullable=True)  # Encrypted
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow(),
                      onupdate=lambda: __import__('datetime').datetime.utcnow())
    created_by = Column(String(100), nullable=True)


# Enhanced Command Tracking
class CommandExecutionDB(Base):
    """Enhanced command execution tracking with idempotency"""
    __tablename__ = 'command_executions'

    id = Column(Integer, primary_key=True, index=True)
    idempotency_key = Column(String(36), unique=True, nullable=False, index=True)
    command_type = Column(String(50), nullable=False, index=True)  # ACTION, NOTIZ, URL
    command_data = Column(JSON, nullable=False)
    event_id = Column(String(36), nullable=True, index=True)
    status = Column(String(50), default='pending', index=True)
    result_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)


# System Health and Monitoring
class SystemMetricsDB(Base):
    """Database model for system metrics and health monitoring"""
    __tablename__ = 'system_metrics'

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(String(500), nullable=False)
    metric_type = Column(String(50), default='gauge')  # gauge, counter, histogram
    labels = Column(JSON, nullable=True)  # Additional labels/tags
    recorded_at = Column(DateTime, default=lambda: __import__('datetime').datetime.utcnow(), index=True)

    # Index for time-series queries
    __table_args__ = (
        Index('idx_metrics_name_time', 'metric_name', 'recorded_at'),
    )