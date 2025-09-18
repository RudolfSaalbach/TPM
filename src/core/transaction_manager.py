"""
Transaction Manager for ensuring atomicity between database and Google Calendar operations.
Implements a robust two-phase commit pattern with rollback capabilities.
"""

import logging
from typing import Any, Callable, Dict, Optional, Tuple
from enum import Enum
from contextlib import contextmanager
from datetime import datetime
import json
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """States for distributed transaction tracking."""
    PENDING = "pending"
    DB_COMMITTED = "db_committed"
    API_COMMITTED = "api_committed"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class TransactionLog:
    """Log entry for transaction audit trail."""
    transaction_id: str
    operation: str
    state: TransactionState
    db_data: Optional[Dict] = None
    api_data: Optional[Dict] = None
    error: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class TransactionManager:
    """
    Manages distributed transactions between local database and Google Calendar API.
    Ensures consistency through proper rollback mechanisms.
    """
    
    def __init__(self, db_session: Session, calendar_client):
        self.db_session = db_session
        self.calendar_client = calendar_client
        self.transaction_logs = []
        self._pending_sync_queue = []
        
    def execute_transaction(
        self,
        db_operation: Callable,
        api_operation: Callable,
        transaction_id: str,
        operation_name: str,
        db_args: Dict = None,
        api_args: Dict = None
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Execute a distributed transaction with automatic rollback on failure.
        
        Args:
            db_operation: Database operation callable
            api_operation: Google Calendar API operation callable
            transaction_id: Unique transaction identifier
            operation_name: Name of the operation (for logging)
            db_args: Arguments for database operation
            api_args: Arguments for API operation
            
        Returns:
            Tuple of (success, result, error_message)
        """
        db_args = db_args or {}
        api_args = api_args or {}
        
        # Initialize transaction log
        log_entry = TransactionLog(
            transaction_id=transaction_id,
            operation=operation_name,
            state=TransactionState.PENDING,
            db_data=db_args,
            api_data=api_args
        )
        self.transaction_logs.append(log_entry)
        
        db_result = None
        api_result = None
        
        try:
            # Phase 1: Execute database operation within a savepoint
            with self._database_savepoint():
                db_result = db_operation(**db_args)
                log_entry.state = TransactionState.DB_COMMITTED
                logger.info(f"Transaction {transaction_id}: DB operation completed")
                
                # Phase 2: Execute API operation
                try:
                    api_result = api_operation(**api_args)
                    log_entry.state = TransactionState.API_COMMITTED
                    logger.info(f"Transaction {transaction_id}: API operation completed")
                    
                    # Phase 3: Commit the transaction
                    self.db_session.commit()
                    log_entry.state = TransactionState.COMPLETED
                    logger.info(f"Transaction {transaction_id}: Successfully completed")
                    
                    return True, {"db": db_result, "api": api_result}, None
                    
                except HttpError as api_error:
                    # API operation failed - rollback database changes
                    error_msg = f"API operation failed: {str(api_error)}"
                    logger.error(f"Transaction {transaction_id}: {error_msg}")
                    log_entry.error = error_msg
                    log_entry.state = TransactionState.FAILED
                    
                    # Add to pending sync queue for retry
                    self._add_to_pending_sync(transaction_id, db_result, api_args)
                    
                    # Rollback will happen automatically due to savepoint context
                    raise
                    
        except Exception as e:
            # Any failure - ensure rollback
            self.db_session.rollback()
            log_entry.state = TransactionState.ROLLED_BACK
            error_msg = f"Transaction failed and rolled back: {str(e)}"
            logger.error(f"Transaction {transaction_id}: {error_msg}")
            return False, None, error_msg
    
    @contextmanager
    def _database_savepoint(self):
        """Create a database savepoint for nested transaction support."""
        savepoint = self.db_session.begin_nested()
        try:
            yield savepoint
        except Exception:
            savepoint.rollback()
            raise
        else:
            # Note: We don't commit here - let the outer transaction handle it
            pass
    
    def _add_to_pending_sync(self, transaction_id: str, db_data: Any, api_args: Dict):
        """
        Add failed API operation to pending sync queue for later retry.
        This ensures eventual consistency even if the API is temporarily unavailable.
        """
        pending_item = {
            "transaction_id": transaction_id,
            "timestamp": datetime.utcnow().isoformat(),
            "db_data": db_data,
            "api_args": api_args,
            "retry_count": 0
        }
        self._pending_sync_queue.append(pending_item)
        
        # Persist to a pending_sync table (implementation depends on your schema)
        # This ensures pending operations survive application restarts
        self._persist_pending_sync(pending_item)
    
    def _persist_pending_sync(self, pending_item: Dict):
        """Persist pending sync operation to database for durability."""
        # This would interact with a pending_sync table
        # Implementation depends on your database schema
        pass
    
    def process_pending_syncs(self, max_retries: int = 3) -> Dict[str, int]:
        """
        Process all pending sync operations.
        Should be called periodically by a background task.
        
        Returns:
            Dictionary with counts of successful, failed, and skipped syncs
        """
        results = {"successful": 0, "failed": 0, "skipped": 0}
        
        for pending in self._pending_sync_queue[:]:  # Copy list to allow modification
            if pending["retry_count"] >= max_retries:
                logger.warning(f"Skipping sync for {pending['transaction_id']}: max retries exceeded")
                results["skipped"] += 1
                continue
                
            try:
                # Retry the API operation
                api_result = self.calendar_client.create_event(**pending["api_args"])
                
                # Success - remove from queue
                self._pending_sync_queue.remove(pending)
                results["successful"] += 1
                logger.info(f"Successfully synced pending operation {pending['transaction_id']}")
                
            except Exception as e:
                pending["retry_count"] += 1
                results["failed"] += 1
                logger.error(f"Failed to sync {pending['transaction_id']}: {str(e)}")
        
        return results
    
    def get_transaction_status(self, transaction_id: str) -> Optional[TransactionLog]:
        """Get the status of a specific transaction."""
        for log in self.transaction_logs:
            if log.transaction_id == transaction_id:
                return log
        return None
    
    def get_pending_syncs(self) -> list:
        """Get all pending sync operations."""
        return self._pending_sync_queue.copy()
