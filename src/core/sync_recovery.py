"""
Background task for processing pending synchronizations.
Ensures eventual consistency between database and Google Calendar.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from src.core.transaction_manager import TransactionManager
from src.database.models import PendingSync
from src.database.session import SessionLocal

logger = logging.getLogger(__name__)


class SyncRecoveryService:
    """
    Service for recovering failed synchronizations.
    Runs as a background task to ensure eventual consistency.
    """
    
    def __init__(self, calendar_client, check_interval: int = 300):
        """
        Initialize the sync recovery service.
        
        Args:
            calendar_client: Google Calendar client instance
            check_interval: Seconds between sync attempts (default: 5 minutes)
        """
        self.calendar_client = calendar_client
        self.check_interval = check_interval
        self._running = False
        
    async def start(self):
        """Start the background sync recovery task."""
        self._running = True
        logger.info("Sync recovery service started")
        
        while self._running:
            try:
                await self._process_pending_syncs()
            except Exception as e:
                logger.error(f"Error in sync recovery service: {str(e)}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Stop the background sync recovery task."""
        self._running = False
        logger.info("Sync recovery service stopped")
    
    async def _process_pending_syncs(self):
        """Process all pending synchronizations."""
        with SessionLocal() as db:
            transaction_manager = TransactionManager(db, self.calendar_client)
            
            # Get pending syncs older than 1 minute (to avoid race conditions)
            cutoff_time = datetime.utcnow() - timedelta(minutes=1)
            pending_syncs = db.query(PendingSync).filter(
                PendingSync.created_at < cutoff_time,
                PendingSync.status == 'pending'
            ).all()
            
            if not pending_syncs:
                return
            
            logger.info(f"Processing {len(pending_syncs)} pending synchronizations")
            
            for pending in pending_syncs:
                try:
                    # Retry the sync operation
                    if pending.operation_type == 'create':
                        await self._retry_create_sync(pending, db)
                    elif pending.operation_type == 'update':
                        await self._retry_update_sync(pending, db)
                    elif pending.operation_type == 'delete':
                        await self._retry_delete_sync(pending, db)
                    
                    # Mark as completed
                    pending.status = 'completed'
                    pending.completed_at = datetime.utcnow()
                    db.commit()
                    
                    logger.info(f"Successfully synced pending operation {pending.transaction_id}")
                    
                except Exception as e:
                    pending.retry_count += 1
                    pending.last_error = str(e)
                    
                    # Max retries exceeded - mark as failed
                    if pending.retry_count >= 3:
                        pending.status = 'failed'
                        logger.error(f"Permanently failed to sync {pending.transaction_id}: {str(e)}")
                    
                    db.commit()
    
    async def _retry_create_sync(self, pending: PendingSync, db: Session):
        """Retry a failed create operation."""
        # Implementation depends on your specific needs
        pass
    
    async def _retry_update_sync(self, pending: PendingSync, db: Session):
        """Retry a failed update operation."""
        # Implementation depends on your specific needs
        pass
    
    async def _retry_delete_sync(self, pending: PendingSync, db: Session):
        """Retry a failed delete operation."""
        # Implementation depends on your specific needs
        pass
