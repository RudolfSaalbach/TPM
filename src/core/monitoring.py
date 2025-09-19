"""
Production Monitoring and Health Checks for Chronos Engine
Comprehensive system monitoring with metrics collection and alerting
"""

import asyncio
import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from collections import deque, defaultdict

from src.core.logging_manager import get_logger, LogCategory
from src.core.schema_extensions import SystemMetricsDB


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class HealthCheck:
    """Health check definition"""
    name: str
    check_function: Callable
    interval_seconds: int = 60
    timeout_seconds: int = 10
    critical: bool = False
    description: str = ""


@dataclass
class Metric:
    """Metric data point"""
    name: str
    value: float
    metric_type: MetricType
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    """Overall system health status"""
    status: HealthStatus
    timestamp: datetime
    checks: List[HealthCheckResult]
    metrics: Dict[str, Any]
    uptime_seconds: float


class MetricsCollector:
    """Collects and stores application metrics"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._metrics = defaultdict(lambda: deque(maxlen=max_history))
        self._lock = threading.Lock()
        self.logger = get_logger('metrics_collector')

    def record_metric(self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE,
                     tags: Dict[str, str] = None):
        """Record a metric value"""
        metric = Metric(
            name=name,
            value=value,
            metric_type=metric_type,
            tags=tags or {}
        )

        with self._lock:
            self._metrics[name].append(metric)

        self.logger.debug(f"Recorded metric: {name}={value}", category=LogCategory.PERFORMANCE,
                         metric_name=name, metric_value=value, metric_type=metric_type.value)

    def increment_counter(self, name: str, value: float = 1.0, tags: Dict[str, str] = None):
        """Increment a counter metric"""
        # Get current value and add to it
        current = self.get_latest_value(name) or 0
        self.record_metric(name, current + value, MetricType.COUNTER, tags)

    def record_timer(self, name: str, duration_ms: float, tags: Dict[str, str] = None):
        """Record a timer metric"""
        self.record_metric(name, duration_ms, MetricType.TIMER, tags)

    def get_latest_value(self, name: str) -> Optional[float]:
        """Get the latest value for a metric"""
        with self._lock:
            metrics = self._metrics.get(name)
            return metrics[-1].value if metrics else None

    def get_metric_history(self, name: str, limit: int = 100) -> List[Metric]:
        """Get metric history"""
        with self._lock:
            metrics = self._metrics.get(name, deque())
            return list(metrics)[-limit:]

    def get_all_metrics(self) -> Dict[str, List[Metric]]:
        """Get all metrics"""
        with self._lock:
            return {name: list(metrics) for name, metrics in self._metrics.items()}

    def get_summary_stats(self, name: str, window_minutes: int = 60) -> Dict[str, float]:
        """Get summary statistics for a metric over a time window"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)

        with self._lock:
            metrics = self._metrics.get(name, deque())
            recent_values = [m.value for m in metrics if m.timestamp >= cutoff_time]

        if not recent_values:
            return {}

        return {
            'count': len(recent_values),
            'min': min(recent_values),
            'max': max(recent_values),
            'avg': sum(recent_values) / len(recent_values),
            'latest': recent_values[-1] if recent_values else 0
        }


class SystemMonitor:
    """System resource monitoring"""

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.logger = get_logger('system_monitor')
        self._monitoring = False
        self._monitor_task = None

    async def start_monitoring(self, interval_seconds: int = 30):
        """Start system monitoring"""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval_seconds))
        self.logger.info("System monitoring started", category=LogCategory.SYSTEM)

    async def stop_monitoring(self):
        """Stop system monitoring"""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self.logger.info("System monitoring stopped", category=LogCategory.SYSTEM)

    async def _monitor_loop(self, interval_seconds: int):
        """Main monitoring loop"""
        while self._monitoring:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in system monitoring", category=LogCategory.SYSTEM,
                                exception=e)
                await asyncio.sleep(interval_seconds)

    async def _collect_system_metrics(self):
        """Collect system metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            self.metrics_collector.record_metric('system.cpu_percent', cpu_percent)

            # Memory metrics
            memory = psutil.virtual_memory()
            self.metrics_collector.record_metric('system.memory_percent', memory.percent)
            self.metrics_collector.record_metric('system.memory_used_bytes', memory.used)
            self.metrics_collector.record_metric('system.memory_available_bytes', memory.available)

            # Disk metrics
            disk = psutil.disk_usage('.')
            self.metrics_collector.record_metric('system.disk_percent', (disk.used / disk.total) * 100)
            self.metrics_collector.record_metric('system.disk_used_bytes', disk.used)
            self.metrics_collector.record_metric('system.disk_free_bytes', disk.free)

            # Network metrics
            network = psutil.net_io_counters()
            self.metrics_collector.record_metric('system.network_bytes_sent', network.bytes_sent, MetricType.COUNTER)
            self.metrics_collector.record_metric('system.network_bytes_recv', network.bytes_recv, MetricType.COUNTER)

            # Process metrics
            process = psutil.Process()
            process_memory = process.memory_info()
            self.metrics_collector.record_metric('process.memory_rss_bytes', process_memory.rss)
            self.metrics_collector.record_metric('process.memory_vms_bytes', process_memory.vms)
            self.metrics_collector.record_metric('process.cpu_percent', process.cpu_percent())
            self.metrics_collector.record_metric('process.num_threads', process.num_threads())

            # File descriptor count (Unix only)
            try:
                self.metrics_collector.record_metric('process.num_fds', process.num_fds())
            except AttributeError:
                pass  # Windows doesn't have num_fds

        except Exception as e:
            self.logger.error("Failed to collect system metrics", category=LogCategory.SYSTEM,
                            exception=e)


class HealthChecker:
    """Health check manager"""

    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory
        self.logger = get_logger('health_checker')
        self._checks: Dict[str, HealthCheck] = {}
        self._results: Dict[str, HealthCheckResult] = {}
        self._checking = False
        self._check_task = None
        self.start_time = time.time()

    def register_check(self, check: HealthCheck):
        """Register a health check"""
        self._checks[check.name] = check
        self.logger.info(f"Registered health check: {check.name}", category=LogCategory.SYSTEM)

    def unregister_check(self, name: str):
        """Unregister a health check"""
        if name in self._checks:
            del self._checks[name]
            if name in self._results:
                del self._results[name]

    async def start_checking(self):
        """Start health checking"""
        if self._checking:
            return

        self._checking = True
        self._check_task = asyncio.create_task(self._check_loop())
        self.logger.info("Health checking started", category=LogCategory.SYSTEM)

    async def stop_checking(self):
        """Stop health checking"""
        self._checking = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Health checking stopped", category=LogCategory.SYSTEM)

    async def _check_loop(self):
        """Main health checking loop"""
        while self._checking:
            try:
                # Run all checks
                for check in self._checks.values():
                    if self._checking:  # Check if still running
                        await self._run_check(check)

                # Sleep until next check cycle
                min_interval = min((check.interval_seconds for check in self._checks.values()), default=60)
                await asyncio.sleep(min_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in health check loop", category=LogCategory.SYSTEM,
                                exception=e)
                await asyncio.sleep(60)

    async def _run_check(self, check: HealthCheck):
        """Run a single health check"""
        # Check if it's time to run this check
        last_result = self._results.get(check.name)
        if last_result:
            time_since_last = (datetime.utcnow() - last_result.timestamp).total_seconds()
            if time_since_last < check.interval_seconds:
                return

        start_time = time.time()
        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                self._execute_check(check),
                timeout=check.timeout_seconds
            )

            duration_ms = (time.time() - start_time) * 1000

            check_result = HealthCheckResult(
                name=check.name,
                status=result.get('status', HealthStatus.HEALTHY),
                message=result.get('message', 'OK'),
                duration_ms=duration_ms,
                details=result.get('details', {})
            )

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            check_result = HealthCheckResult(
                name=check.name,
                status=HealthStatus.CRITICAL,
                message=f"Health check timed out after {check.timeout_seconds}s",
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            check_result = HealthCheckResult(
                name=check.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                duration_ms=duration_ms
            )

        self._results[check.name] = check_result

        # Log result
        if check_result.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
            self.logger.error(f"Health check failed: {check.name} - {check_result.message}",
                            category=LogCategory.SYSTEM, health_check=check.name,
                            status=check_result.status.value)
        else:
            self.logger.debug(f"Health check passed: {check.name}",
                            category=LogCategory.SYSTEM, health_check=check.name)

    async def _execute_check(self, check: HealthCheck) -> Dict[str, Any]:
        """Execute a health check function"""
        if asyncio.iscoroutinefunction(check.check_function):
            return await check.check_function()
        else:
            return check.check_function()

    async def get_health_status(self) -> SystemHealth:
        """Get overall system health status"""
        # Determine overall status
        overall_status = HealthStatus.HEALTHY
        critical_failed = False
        any_failed = False

        for check_name, check in self._checks.items():
            result = self._results.get(check_name)
            if result:
                if result.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
                    any_failed = True
                    if check.critical:
                        critical_failed = True

        if critical_failed:
            overall_status = HealthStatus.CRITICAL
        elif any_failed:
            overall_status = HealthStatus.DEGRADED

        # Get uptime
        uptime_seconds = time.time() - self.start_time

        return SystemHealth(
            status=overall_status,
            timestamp=datetime.utcnow(),
            checks=list(self._results.values()),
            metrics={},  # Will be populated by monitor
            uptime_seconds=uptime_seconds
        )


class ApplicationMonitor:
    """Main application monitoring service"""

    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory
        self.metrics_collector = MetricsCollector()
        self.system_monitor = SystemMonitor(self.metrics_collector)
        self.health_checker = HealthChecker(db_session_factory)
        self.logger = get_logger('application_monitor')
        self._running = False

        # Register default health checks
        self._register_default_checks()

    def _register_default_checks(self):
        """Register default health checks"""
        # Database health check
        if self.db_session_factory:
            self.health_checker.register_check(HealthCheck(
                name="database",
                check_function=self._check_database_health,
                interval_seconds=60,
                critical=True,
                description="Database connectivity and basic operations"
            ))

        # Disk space check
        self.health_checker.register_check(HealthCheck(
            name="disk_space",
            check_function=self._check_disk_space,
            interval_seconds=300,  # 5 minutes
            critical=True,
            description="Available disk space"
        ))

        # Memory check
        self.health_checker.register_check(HealthCheck(
            name="memory",
            check_function=self._check_memory_usage,
            interval_seconds=60,
            critical=False,
            description="Memory usage levels"
        ))

    async def _check_database_health(self) -> Dict[str, Any]:
        """Check database health"""
        if not self.db_session_factory:
            return {
                'status': HealthStatus.HEALTHY,
                'message': 'Database not configured'
            }

        try:
            from sqlalchemy import text

            async with self.db_session_factory() as session:
                await session.execute(text("SELECT 1"))
                return {
                    'status': HealthStatus.HEALTHY,
                    'message': 'Database connection OK'
                }

        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f'Database connection failed: {str(e)}'
            }

    async def _check_disk_space(self) -> Dict[str, Any]:
        """Check disk space"""
        try:
            disk = psutil.disk_usage('.')
            free_percent = (disk.free / disk.total) * 100

            if free_percent < 5:
                status = HealthStatus.CRITICAL
                message = f"Critical: Only {free_percent:.1f}% disk space remaining"
            elif free_percent < 10:
                status = HealthStatus.UNHEALTHY
                message = f"Warning: Only {free_percent:.1f}% disk space remaining"
            elif free_percent < 20:
                status = HealthStatus.DEGRADED
                message = f"Low disk space: {free_percent:.1f}% remaining"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk space OK: {free_percent:.1f}% free"

            return {
                'status': status,
                'message': message,
                'details': {
                    'free_percent': free_percent,
                    'free_bytes': disk.free,
                    'total_bytes': disk.total
                }
            }

        except Exception as e:
            return {
                'status': HealthStatus.UNHEALTHY,
                'message': f'Failed to check disk space: {str(e)}'
            }

    async def _check_memory_usage(self) -> Dict[str, Any]:
        """Check memory usage"""
        try:
            memory = psutil.virtual_memory()

            if memory.percent > 95:
                status = HealthStatus.CRITICAL
                message = f"Critical: Memory usage at {memory.percent:.1f}%"
            elif memory.percent > 90:
                status = HealthStatus.UNHEALTHY
                message = f"High memory usage: {memory.percent:.1f}%"
            elif memory.percent > 80:
                status = HealthStatus.DEGRADED
                message = f"Elevated memory usage: {memory.percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage OK: {memory.percent:.1f}%"

            return {
                'status': status,
                'message': message,
                'details': {
                    'percent': memory.percent,
                    'used_bytes': memory.used,
                    'available_bytes': memory.available
                }
            }

        except Exception as e:
            return {
                'status': HealthStatus.UNHEALTHY,
                'message': f'Failed to check memory usage: {str(e)}'
            }

    async def start(self):
        """Start monitoring services"""
        if self._running:
            return

        self._running = True

        try:
            await self.system_monitor.start_monitoring()
            await self.health_checker.start_checking()

            self.logger.info("Application monitoring started", category=LogCategory.SYSTEM)

        except Exception as e:
            self.logger.error("Failed to start monitoring", category=LogCategory.SYSTEM,
                            exception=e)
            raise

    async def stop(self):
        """Stop monitoring services"""
        if not self._running:
            return

        self._running = False

        try:
            await self.system_monitor.stop_monitoring()
            await self.health_checker.stop_checking()

            self.logger.info("Application monitoring stopped", category=LogCategory.SYSTEM)

        except Exception as e:
            self.logger.error("Error stopping monitoring", category=LogCategory.SYSTEM,
                            exception=e)

    async def get_health_status(self) -> SystemHealth:
        """Get overall health status with metrics"""
        health = await self.health_checker.get_health_status()

        # Add metrics summary
        health.metrics = {
            'cpu_percent': self.metrics_collector.get_latest_value('system.cpu_percent'),
            'memory_percent': self.metrics_collector.get_latest_value('system.memory_percent'),
            'disk_percent': self.metrics_collector.get_latest_value('system.disk_percent'),
            'process_memory_mb': (self.metrics_collector.get_latest_value('process.memory_rss_bytes') or 0) / 1024 / 1024
        }

        return health

    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics"""
        return self.metrics_collector.get_all_metrics()


# Global monitor instance
app_monitor = ApplicationMonitor()