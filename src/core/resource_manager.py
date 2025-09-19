"""
Resource Management for Chronos Engine
Proper cleanup, memory management, and resource lifecycle handling
"""

import asyncio
import weakref
import threading
import time
import gc
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import tracemalloc
from concurrent.futures import ThreadPoolExecutor

from src.core.logging_manager import get_logger, LogCategory


@dataclass
class ResourceInfo:
    """Information about a managed resource"""
    resource_id: str
    resource_type: str
    created_at: float
    last_accessed: float
    cleanup_function: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResourceTracker:
    """Tracks resources for proper cleanup and monitoring"""

    def __init__(self):
        self._resources: Dict[str, ResourceInfo] = {}
        self._weak_refs: Set[weakref.ref] = set()
        self._lock = threading.Lock()
        self.logger = get_logger('resource_tracker')

    def register_resource(self, resource: Any, resource_type: str,
                         cleanup_function: Optional[Callable] = None,
                         metadata: Dict[str, Any] = None) -> str:
        """Register a resource for tracking"""
        resource_id = f"{resource_type}_{id(resource)}"
        current_time = time.time()

        with self._lock:
            # Create weak reference with cleanup callback
            weak_ref = weakref.ref(resource, lambda ref: self._on_resource_deleted(ref, resource_id))
            self._weak_refs.add(weak_ref)

            # Store resource info
            self._resources[resource_id] = ResourceInfo(
                resource_id=resource_id,
                resource_type=resource_type,
                created_at=current_time,
                last_accessed=current_time,
                cleanup_function=cleanup_function,
                metadata=metadata or {}
            )

        self.logger.debug(f"Registered resource: {resource_type} ({resource_id})",
                         category=LogCategory.SYSTEM, resource_type=resource_type,
                         resource_id=resource_id)

        return resource_id

    def _on_resource_deleted(self, weak_ref: weakref.ref, resource_id: str):
        """Callback when a resource is garbage collected"""
        with self._lock:
            self._weak_refs.discard(weak_ref)

            if resource_id in self._resources:
                resource_info = self._resources.pop(resource_id)

                # Run cleanup function if provided
                if resource_info.cleanup_function:
                    try:
                        resource_info.cleanup_function()
                    except Exception as e:
                        self.logger.error(f"Error in resource cleanup: {e}",
                                        category=LogCategory.SYSTEM,
                                        resource_id=resource_id, exception=e)

                self.logger.debug(f"Resource garbage collected: {resource_info.resource_type} ({resource_id})",
                                category=LogCategory.SYSTEM, resource_type=resource_info.resource_type,
                                resource_id=resource_id)

    def touch_resource(self, resource_id: str):
        """Update last accessed time for a resource"""
        with self._lock:
            if resource_id in self._resources:
                self._resources[resource_id].last_accessed = time.time()

    def get_resource_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked resources"""
        with self._lock:
            stats = {
                'total_resources': len(self._resources),
                'by_type': {},
                'oldest_resource_age': 0,
                'resources': []
            }

            current_time = time.time()
            oldest_age = 0

            for resource_info in self._resources.values():
                resource_type = resource_info.resource_type
                age = current_time - resource_info.created_at

                if resource_type not in stats['by_type']:
                    stats['by_type'][resource_type] = 0
                stats['by_type'][resource_type] += 1

                if age > oldest_age:
                    oldest_age = age

                stats['resources'].append({
                    'id': resource_info.resource_id,
                    'type': resource_info.resource_type,
                    'age_seconds': age,
                    'last_accessed_seconds_ago': current_time - resource_info.last_accessed,
                    'metadata': resource_info.metadata
                })

            stats['oldest_resource_age'] = oldest_age
            return stats

    def cleanup_stale_resources(self, max_age_seconds: int = 3600):
        """Force cleanup of stale resources"""
        current_time = time.time()
        stale_resources = []

        with self._lock:
            for resource_id, resource_info in self._resources.items():
                if current_time - resource_info.last_accessed > max_age_seconds:
                    stale_resources.append((resource_id, resource_info))

        # Cleanup outside of lock
        for resource_id, resource_info in stale_resources:
            if resource_info.cleanup_function:
                try:
                    resource_info.cleanup_function()
                    self.logger.info(f"Cleaned up stale resource: {resource_info.resource_type}",
                                   category=LogCategory.SYSTEM, resource_id=resource_id)
                except Exception as e:
                    self.logger.error(f"Error cleaning up stale resource: {e}",
                                    category=LogCategory.SYSTEM, resource_id=resource_id,
                                    exception=e)

        return len(stale_resources)


class ConnectionPool:
    """Generic connection pool with proper resource management"""

    def __init__(self, create_connection: Callable, max_connections: int = 10,
                 max_idle_time: int = 300, validate_connection: Optional[Callable] = None):
        self.create_connection = create_connection
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.validate_connection = validate_connection
        self._pool: List[Any] = []
        self._in_use: Set[Any] = set()
        self._connection_times: Dict[Any, float] = {}
        self._lock = asyncio.Lock()
        self.logger = get_logger('connection_pool')

    async def get_connection(self):
        """Get a connection from the pool"""
        async with self._lock:
            # Clean up expired connections
            await self._cleanup_expired_connections()

            # Try to get from pool
            while self._pool:
                connection = self._pool.pop()

                # Validate connection if validator provided
                if self.validate_connection:
                    try:
                        if await self._safe_validate(connection):
                            self._in_use.add(connection)
                            return connection
                        else:
                            await self._safe_close(connection)
                    except Exception:
                        await self._safe_close(connection)
                else:
                    self._in_use.add(connection)
                    return connection

            # Create new connection if under limit
            if len(self._in_use) < self.max_connections:
                connection = await self._safe_create()
                if connection:
                    self._in_use.add(connection)
                    return connection

            # Pool exhausted
            raise RuntimeError("Connection pool exhausted")

    async def return_connection(self, connection):
        """Return a connection to the pool"""
        async with self._lock:
            if connection in self._in_use:
                self._in_use.remove(connection)
                self._pool.append(connection)
                self._connection_times[connection] = time.time()

    async def close_connection(self, connection):
        """Close and remove a connection"""
        async with self._lock:
            self._in_use.discard(connection)
            if connection in self._pool:
                self._pool.remove(connection)
            self._connection_times.pop(connection, None)
            await self._safe_close(connection)

    async def _cleanup_expired_connections(self):
        """Remove expired connections from pool"""
        current_time = time.time()
        expired = []

        for connection in self._pool[:]:
            connection_time = self._connection_times.get(connection, current_time)
            if current_time - connection_time > self.max_idle_time:
                expired.append(connection)

        for connection in expired:
            self._pool.remove(connection)
            self._connection_times.pop(connection, None)
            await self._safe_close(connection)

    async def _safe_create(self):
        """Safely create a connection"""
        try:
            if asyncio.iscoroutinefunction(self.create_connection):
                return await self.create_connection()
            else:
                return self.create_connection()
        except Exception as e:
            self.logger.error("Failed to create connection", category=LogCategory.SYSTEM,
                            exception=e)
            return None

    async def _safe_validate(self, connection) -> bool:
        """Safely validate a connection"""
        try:
            if asyncio.iscoroutinefunction(self.validate_connection):
                return await self.validate_connection(connection)
            else:
                return self.validate_connection(connection)
        except Exception:
            return False

    async def _safe_close(self, connection):
        """Safely close a connection"""
        try:
            if hasattr(connection, 'close'):
                if asyncio.iscoroutinefunction(connection.close):
                    await connection.close()
                else:
                    connection.close()
        except Exception as e:
            self.logger.error("Error closing connection", category=LogCategory.SYSTEM,
                            exception=e)

    async def close_all(self):
        """Close all connections in the pool"""
        async with self._lock:
            all_connections = list(self._pool) + list(self._in_use)
            self._pool.clear()
            self._in_use.clear()
            self._connection_times.clear()

            for connection in all_connections:
                await self._safe_close(connection)


class MemoryManager:
    """Memory management and monitoring"""

    def __init__(self):
        self.logger = get_logger('memory_manager')
        self._monitoring = False
        self._monitor_task = None
        self._gc_stats = {'collections': 0, 'freed_objects': 0}

        # Enable tracemalloc for memory profiling
        if not tracemalloc.is_tracing():
            tracemalloc.start()

    async def start_monitoring(self, interval_seconds: int = 60):
        """Start memory monitoring"""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval_seconds))
        self.logger.info("Memory monitoring started", category=LogCategory.SYSTEM)

    async def stop_monitoring(self):
        """Stop memory monitoring"""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self, interval_seconds: int):
        """Memory monitoring loop"""
        while self._monitoring:
            try:
                await self._check_memory_usage()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in memory monitoring", category=LogCategory.SYSTEM,
                                exception=e)
                await asyncio.sleep(interval_seconds)

    async def _check_memory_usage(self):
        """Check current memory usage"""
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()

            # Get memory usage in MB
            rss_mb = memory_info.rss / 1024 / 1024
            vms_mb = memory_info.vms / 1024 / 1024

            # Get tracemalloc statistics
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                traced_mb = current / 1024 / 1024
                peak_mb = peak / 1024 / 1024

                self.logger.debug("Memory usage", category=LogCategory.PERFORMANCE,
                                rss_mb=rss_mb, vms_mb=vms_mb, traced_mb=traced_mb, peak_mb=peak_mb)

                # Warn on high memory usage
                if rss_mb > 500:  # 500MB
                    self.logger.warning(f"High memory usage: {rss_mb:.1f}MB RSS",
                                      category=LogCategory.SYSTEM, memory_mb=rss_mb)

        except Exception as e:
            self.logger.error("Failed to check memory usage", category=LogCategory.SYSTEM,
                            exception=e)

    def force_garbage_collection(self) -> Dict[str, int]:
        """Force garbage collection and return statistics"""
        before_objects = len(gc.get_objects())

        # Force collection of all generations
        collected = sum(gc.collect(generation) for generation in range(3))

        after_objects = len(gc.get_objects())
        freed_objects = before_objects - after_objects

        self._gc_stats['collections'] += 1
        self._gc_stats['freed_objects'] += freed_objects

        self.logger.info(f"Garbage collection freed {freed_objects} objects",
                        category=LogCategory.SYSTEM, freed_objects=freed_objects,
                        collected=collected)

        return {
            'objects_before': before_objects,
            'objects_after': after_objects,
            'freed_objects': freed_objects,
            'collected': collected
        }

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()

            stats = {
                'rss_bytes': memory_info.rss,
                'vms_bytes': memory_info.vms,
                'gc_stats': self._gc_stats.copy()
            }

            # Add tracemalloc stats if available
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                stats.update({
                    'traced_current_bytes': current,
                    'traced_peak_bytes': peak
                })

                # Get top memory allocations
                top_stats = tracemalloc.take_snapshot().statistics('lineno')[:10]
                stats['top_allocations'] = [
                    {
                        'size_bytes': stat.size,
                        'count': stat.count,
                        'filename': stat.traceback.format()[0] if stat.traceback else 'unknown'
                    }
                    for stat in top_stats
                ]

            return stats

        except Exception as e:
            self.logger.error("Failed to get memory stats", category=LogCategory.SYSTEM,
                            exception=e)
            return {'error': str(e)}


class TaskManager:
    """Manages async tasks with proper cleanup"""

    def __init__(self):
        self._tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self.logger = get_logger('task_manager')

    async def create_task(self, coro, name: Optional[str] = None) -> asyncio.Task:
        """Create and track an async task"""
        task = asyncio.create_task(coro, name=name)

        async with self._lock:
            self._tasks.add(task)

        # Add done callback for cleanup
        task.add_done_callback(self._task_done_callback)

        self.logger.debug(f"Created task: {name or 'unnamed'}", category=LogCategory.SYSTEM,
                         task_name=name, total_tasks=len(self._tasks))

        return task

    def _task_done_callback(self, task: asyncio.Task):
        """Callback when task is done"""
        asyncio.create_task(self._remove_task(task))

        # Log task completion or exception
        if task.exception():
            self.logger.error(f"Task failed: {task.get_name()}",
                            category=LogCategory.SYSTEM, task_name=task.get_name(),
                            exception=task.exception())
        else:
            self.logger.debug(f"Task completed: {task.get_name()}",
                            category=LogCategory.SYSTEM, task_name=task.get_name())

    async def _remove_task(self, task: asyncio.Task):
        """Remove task from tracking"""
        async with self._lock:
            self._tasks.discard(task)

    async def cancel_all_tasks(self, timeout: float = 30.0):
        """Cancel all tracked tasks"""
        async with self._lock:
            tasks_to_cancel = list(self._tasks)

        if not tasks_to_cancel:
            return

        self.logger.info(f"Cancelling {len(tasks_to_cancel)} tasks",
                        category=LogCategory.SYSTEM)

        # Cancel all tasks
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()

        # Wait for cancellation with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            self.logger.warning("Task cancellation timed out", category=LogCategory.SYSTEM)

    def get_task_stats(self) -> Dict[str, Any]:
        """Get task statistics"""
        return {
            'total_tasks': len(self._tasks),
            'task_names': [task.get_name() for task in self._tasks if not task.done()]
        }


class ResourceManager:
    """Main resource manager orchestrating all resource management"""

    def __init__(self):
        self.resource_tracker = ResourceTracker()
        self.memory_manager = MemoryManager()
        self.task_manager = TaskManager()
        self._thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chronos-worker")
        self.logger = get_logger('resource_manager')
        self._shutdown = False

    async def start(self):
        """Start resource management services"""
        await self.memory_manager.start_monitoring()
        self.logger.info("Resource manager started", category=LogCategory.SYSTEM)

    async def shutdown(self, timeout: float = 30.0):
        """Shutdown all resource management services"""
        if self._shutdown:
            return

        self._shutdown = True
        self.logger.info("Shutting down resource manager", category=LogCategory.SYSTEM)

        try:
            # Cancel all async tasks
            await self.task_manager.cancel_all_tasks(timeout)

            # Stop memory monitoring
            await self.memory_manager.stop_monitoring()

            # Shutdown thread pool
            self._thread_pool.shutdown(wait=True, timeout=timeout)

            # Force garbage collection
            self.memory_manager.force_garbage_collection()

            self.logger.info("Resource manager shutdown complete", category=LogCategory.SYSTEM)

        except Exception as e:
            self.logger.error("Error during resource manager shutdown",
                            category=LogCategory.SYSTEM, exception=e)

    def register_resource(self, resource: Any, resource_type: str,
                         cleanup_function: Optional[Callable] = None,
                         metadata: Dict[str, Any] = None) -> str:
        """Register a resource for tracking"""
        return self.resource_tracker.register_resource(
            resource, resource_type, cleanup_function, metadata
        )

    async def create_task(self, coro, name: Optional[str] = None) -> asyncio.Task:
        """Create and track an async task"""
        return await self.task_manager.create_task(coro, name)

    def run_in_thread(self, func: Callable, *args, **kwargs):
        """Run a function in the thread pool"""
        return self._thread_pool.submit(func, *args, **kwargs)

    def get_resource_stats(self) -> Dict[str, Any]:
        """Get comprehensive resource statistics"""
        return {
            'resources': self.resource_tracker.get_resource_stats(),
            'memory': self.memory_manager.get_memory_stats(),
            'tasks': self.task_manager.get_task_stats(),
            'thread_pool': {
                'max_workers': self._thread_pool._max_workers,
                'active_threads': getattr(self._thread_pool, '_threads', 0)
            }
        }


# Global resource manager
resource_manager = ResourceManager()


# Context manager for automatic resource cleanup
@asynccontextmanager
async def managed_resource(resource: Any, resource_type: str,
                          cleanup_function: Optional[Callable] = None):
    """Context manager for automatic resource cleanup"""
    resource_id = resource_manager.register_resource(
        resource, resource_type, cleanup_function
    )

    try:
        yield resource
    finally:
        if cleanup_function:
            try:
                if asyncio.iscoroutinefunction(cleanup_function):
                    await cleanup_function()
                else:
                    cleanup_function()
            except Exception as e:
                logger = get_logger('managed_resource')
                logger.error(f"Error in resource cleanup: {e}",
                           category=LogCategory.SYSTEM, resource_id=resource_id,
                           exception=e)