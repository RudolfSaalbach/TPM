"""
Additional database model for tracking pending synchronizations.
Add this to your existing models.
"""

from sqlalchemy import Column, String, DateTime, Integer, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class PendingSync(Base):
    """
    Tracks synchronization operations that need to be retried.
    Ensures eventual consistency between database and external services.
    """
    __tablename__ = 'pending_syncs'
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(36), unique=True, nullable=False, index=True)
    operation_type = Column(String(20), nullable=False)  # create, update, delete
    entity_type = Column(String(50), nullable=False)  # event, task, etc.
    entity_id = Column(String(36), nullable=False)
    
    # Store the data needed to retry the operation
    db_data = Column(JSON, nullable=True)
    api_data = Column(JSON, nullable=True)
    
    # Tracking fields
    status = Column(String(20), default='pending')  # pending, completed, failed
    retry_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_attempt_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<PendingSync(transaction_id={self.transaction_id}, status={self.status})>"
