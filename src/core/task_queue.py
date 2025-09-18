"""
Enhanced Task Queue for Chronos Engine v2.1 - Database Integration with Recovery
Persistent task queue with automatic recovery mechanism
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy import select, and_, or_, update

from src.core.models import Task, TaskDB, TaskStatus, TaskPriority
from src.core.database import db_service


class EnhancedTaskQueue:
    """Database-powered task queue with recovery mechanisms"""
    
    def __init__(self, max_concurrent_tasks: int = 5):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.logger = logging.getLogger(__name__)
        
        # Task execution control
        self.is_running = False
        self.worker_task = None
        self.recovery_completed = False
        
        self.logger.info("Enhanced Task Queue initialized with database persistence & recovery")
    
    async def start(self):
        """Start the task queue worker with recovery"""
        if self.is_running:
            return
        
        # Perform recovery first
        await self._perform_recovery()
        
        self.is_running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        
        self.logger.info("✅ Enhanced Task Queue worker started with recovery")
    
    async def stop(self):
        """Stop the task queue worker gracefully"""
        self.is_running = False
        
        # Mark running tasks as interrupted
        await self._mark_running_tasks_as_interrupted()
        
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("🔒 Enhanced Task Queue worker stopped")
    
    async def _perform_recovery(self):
        """Recover tasks after application restart"""
        if self.recovery_completed:
            return
        
        self.logger.info("🔄 Performing task queue recovery...")
        
        try:
            async with db_service.get_session() as session:
                # Find running tasks (these were interrupted)
                running_result = await session.execute(
                    select(TaskDB).where(TaskDB.status == TaskStatus.RUNNING.value)
                )
                running_tasks = running_result.scalars().all()
                
                # Mark running tasks as failed
                for task in running_tasks:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = "Task interrupted by application restart"
                    task.completed_at = datetime.utcnow()
                    
                    self.logger.info(f"❌ Marked interrupted task as failed: {task.name} ({task.id})")
                
                # Find pending tasks
                pending_result = await session.execute(
                    select(TaskDB).where(TaskDB.status == TaskStatus.PENDING.value)
                )
                pending_tasks = pending_result.scalars().all()
                
                await session.commit()
                
                self.logger.info(f"🔄 Recovery completed: {len(running_tasks)} interrupted, {len(pending_tasks)} pending")
                
        except Exception as e:
            self.logger.error(f"❌ Task recovery failed: {e}")
            # Continue anyway - don't block startup
        
        self.recovery_completed = True
    
    async def _mark_running_tasks_as_interrupted(self):
        """Mark currently running tasks as interrupted during shutdown"""
        try:
            async with db_service.get_session() as session:
                await session.execute(
                    update(TaskDB)
                    .where(TaskDB.status == TaskStatus.RUNNING.value)
                    .values(
                        status=TaskStatus.FAILED.value,
                        error_message="Task interrupted by graceful shutdown",
                        completed_at=datetime.utcnow()
                    )
                )
                await session.commit()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to mark tasks as interrupted: {e}")
    
    async def add_task(
        self,
        name: str,
        function: str,
        args: List[Any] = None,
        kwargs: Dict[str, Any] = None,
        priority: TaskPriority = TaskPriority.MEDIUM
    ) -> str:
        """Add task to persistent database queue"""
        
        task = Task(
            name=name,
            function=function,
            args=args or [],
            kwargs=kwargs or {},
            priority=priority,
            status=TaskStatus.PENDING
        )
        
        # Store in database
        async with db_service.get_session() as session:
            session.add(task.to_db_model())
            await session.commit()
        
        self.logger.info(f"📝 Task added to persistent queue: {name} ({task.id})")
        return task.id
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status from database"""
        
        async with db_service.get_session() as session:
            result = await session.execute(
                select(TaskDB).where(TaskDB.id == task_id)
            )
            db_task = result.scalar_one_or_none()
            
            if not db_task:
                return None
            
            task = db_task.to_domain_model()
            return {
                'id': task.id,
                'name': task.name,
                'status': task.status.value,
                'priority': task.priority.name,
                'progress': task.progress,
                'result': task.result,
                'error': task.error,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None
            }
    
    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive queue status from database"""
        
        async with db_service.get_session() as session:
            # Count tasks by status
            result = await session.execute(select(TaskDB))
            all_tasks = result.scalars().all()
            
            status_counts = {}
            for status in TaskStatus:
                status_counts[status.value] = len([t for t in all_tasks if t.status == status.value])
            
            # Get running tasks
            running_tasks = [t for t in all_tasks if t.status == TaskStatus.RUNNING.value]
            
            # Get recent tasks (last 24 hours)
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_tasks = [t for t in all_tasks if t.created_at and t.created_at >= recent_cutoff]
            
            return {
                'is_running': self.is_running,
                'recovery_completed': self.recovery_completed,
                'status_counts': status_counts,
                'running_tasks': len(running_tasks),
                'max_concurrent_tasks': self.max_concurrent_tasks,
                'current_load': len(running_tasks) / self.max_concurrent_tasks,
                'total_tasks': len(all_tasks),
                'recent_tasks_24h': len(recent_tasks)
            }
    
    async def _worker_loop(self):
        """Enhanced worker loop - processes tasks from database with recovery"""
        
        while self.is_running:
            try:
                await self._process_pending_tasks()
                await asyncio.sleep(1)  # Check for new tasks every second
            except Exception as e:
                self.logger.error(f"❌ Error in enhanced task worker loop: {e}")
                await asyncio.sleep(5)
    
    async def _process_pending_tasks(self):
        """Process pending tasks from database with priority ordering"""
        
        async with db_service.get_session() as session:
            # Get running tasks count
            running_result = await session.execute(
                select(TaskDB).where(TaskDB.status == TaskStatus.RUNNING.value)
            )
            running_count = len(running_result.scalars().all())
            
            if running_count >= self.max_concurrent_tasks:
                return  # Already at capacity
            
            # Get pending tasks ordered by priority then creation time
            pending_result = await session.execute(
                select(TaskDB)
                .where(TaskDB.status == TaskStatus.PENDING.value)
                .order_by(
                    TaskDB.priority.desc(),  # Higher priority first
                    TaskDB.created_at.asc()  # Older tasks first within same priority
                )
                .limit(self.max_concurrent_tasks - running_count)
            )
            pending_tasks = pending_result.scalars().all()
            
            for db_task in pending_tasks:
                # Mark as running
                db_task.status = TaskStatus.RUNNING.value
                db_task.started_at = datetime.utcnow()
                await session.commit()
                
                # Execute task in background
                task = db_task.to_domain_model()
                asyncio.create_task(self._execute_task(task))
                
                self.logger.debug(f"🚀 Started task: {task.name} (Priority: {task.priority.name})")
    
    async def _execute_task(self, task: Task):
        """Execute individual task and update database with results"""
        
        try:
            self.logger.info(f"⚡ Executing task: {task.name}")
            
            # Update progress
            await self._update_task_progress(task.id, 10)
            
            # Execute the actual task function
            result = await self._dispatch_task_function(task)
            
            # Update progress
            await self._update_task_progress(task.id, 100)
            
            # Update database with success
            async with db_service.get_session() as session:
                result_update = await session.execute(
                    select(TaskDB).where(TaskDB.id == task.id)
                )
                db_task = result_update.scalar_one_or_none()
                
                if db_task:
                    db_task.status = TaskStatus.COMPLETED.value
                    db_task.result = result
                    db_task.progress = 100
                    db_task.completed_at = datetime.utcnow()
                    await session.commit()
            
            self.logger.info(f"✅ Task completed successfully: {task.name}")
            
        except Exception as e:
            self.logger.error(f"❌ Task execution failed: {task.name} - {e}")
            
            # Update database with error
            async with db_service.get_session() as session:
                result_update = await session.execute(
                    select(TaskDB).where(TaskDB.id == task.id)
                )
                db_task = result_update.scalar_one_or_none()
                
                if db_task:
                    db_task.status = TaskStatus.FAILED.value
                    db_task.error_message = str(e)
                    db_task.completed_at = datetime.utcnow()
                    await session.commit()
    
    async def _update_task_progress(self, task_id: str, progress: int):
        """Update task progress in database"""
        try:
            async with db_service.get_session() as session:
                await session.execute(
                    update(TaskDB)
                    .where(TaskDB.id == task_id)
                    .values(progress=progress)
                )
                await session.commit()
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to update task progress: {e}")
    
    async def _dispatch_task_function(self, task: Task) -> Dict[str, Any]:
        """Dispatch task to appropriate function"""
        
        # Simulate task execution for now
        await asyncio.sleep(2)  # Simulate work
        
        return {
            'success': True,
            'message': f'Task {task.name} completed successfully',
            'function': task.function,
            'args': task.args,
            'kwargs': task.kwargs,
            'timestamp': datetime.utcnow().isoformat()
        }


# Alias for backward compatibility
TaskQueue = EnhancedTaskQueue
