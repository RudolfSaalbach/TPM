"""
Performance Monitor for Chronos Engine v2.1
Tracks system performance, memory usage, and response times
"""

import logging
import time
import psutil
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json

from src.core.models import ChronosEvent


@dataclass
class PerformanceMetric:
    """Performance metric data structure"""
    timestamp: datetime
    metric_type: str
    value: float
    unit: str
    context: Dict[str, Any] = None


class PerformanceMonitor:
    """System performance monitoring and metrics collection"""

    def __init__(self, config: Dict[str, Any] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        self.metrics_buffer = []
        self.max_buffer_size = self.config.get('max_buffer_size', 1000)
        self.collection_interval = self.config.get('collection_interval', 60)  # seconds
        self.is_monitoring = False
        self._monitor_task = None

        # Performance thresholds
        self.thresholds = {
            'memory_usage_percent': 80.0,
            'cpu_usage_percent': 85.0,
            'response_time_ms': 1000.0,
            'event_processing_time_ms': 100.0,
            'database_query_time_ms': 50.0
        }

    async def start_monitoring(self):
        """Start continuous performance monitoring"""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("📊 Performance monitoring started")

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self.logger.info("📊 Performance monitoring stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        try:
            while self.is_monitoring:
                await self._collect_system_metrics()
                await asyncio.sleep(self.collection_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"📊 Error in monitoring loop: {e}")

    async def _collect_system_metrics(self):
        """Collect system performance metrics"""
        try:
            now = datetime.utcnow()

            # Memory metrics
            memory = psutil.virtual_memory()
            self._add_metric(PerformanceMetric(
                timestamp=now,
                metric_type="memory_usage_percent",
                value=memory.percent,
                unit="percent",
                context={"available_gb": round(memory.available / (1024**3), 2)}
            ))

            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            self._add_metric(PerformanceMetric(
                timestamp=now,
                metric_type="cpu_usage_percent",
                value=cpu_percent,
                unit="percent"
            ))

            # Disk metrics
            disk = psutil.disk_usage('/')
            self._add_metric(PerformanceMetric(
                timestamp=now,
                metric_type="disk_usage_percent",
                value=(disk.used / disk.total) * 100,
                unit="percent",
                context={"free_gb": round(disk.free / (1024**3), 2)}
            ))

            # Process-specific metrics
            process = psutil.Process()
            self._add_metric(PerformanceMetric(
                timestamp=now,
                metric_type="process_memory_mb",
                value=process.memory_info().rss / (1024 * 1024),
                unit="mb"
            ))

        except Exception as e:
            self.logger.error(f"📊 Error collecting system metrics: {e}")

    def _add_metric(self, metric: PerformanceMetric):
        """Add metric to buffer with size management"""
        self.metrics_buffer.append(metric)

        # Maintain buffer size
        if len(self.metrics_buffer) > self.max_buffer_size:
            self.metrics_buffer = self.metrics_buffer[-self.max_buffer_size:]

    def time_operation(self, operation_name: str):
        """Decorator/context manager for timing operations"""
        return OperationTimer(self, operation_name)

    async def record_response_time(self, endpoint: str, duration_ms: float):
        """Record API response time"""
        self._add_metric(PerformanceMetric(
            timestamp=datetime.utcnow(),
            metric_type="api_response_time",
            value=duration_ms,
            unit="ms",
            context={"endpoint": endpoint}
        ))

        # Check threshold
        if duration_ms > self.thresholds['response_time_ms']:
            self.logger.warning(f"📊 Slow API response: {endpoint} took {duration_ms:.1f}ms")

    async def record_event_processing_time(self, event_count: int, duration_ms: float):
        """Record event processing performance"""
        self._add_metric(PerformanceMetric(
            timestamp=datetime.utcnow(),
            metric_type="event_processing_time",
            value=duration_ms,
            unit="ms",
            context={"event_count": event_count}
        ))

        avg_time_per_event = duration_ms / max(1, event_count)
        if avg_time_per_event > self.thresholds['event_processing_time_ms']:
            self.logger.warning(f"📊 Slow event processing: {avg_time_per_event:.1f}ms per event")

    async def record_database_query_time(self, query_type: str, duration_ms: float):
        """Record database query performance"""
        self._add_metric(PerformanceMetric(
            timestamp=datetime.utcnow(),
            metric_type="database_query_time",
            value=duration_ms,
            unit="ms",
            context={"query_type": query_type}
        ))

        if duration_ms > self.thresholds['database_query_time_ms']:
            self.logger.warning(f"📊 Slow database query: {query_type} took {duration_ms:.1f}ms")

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics snapshot"""
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            disk = psutil.disk_usage('/')
            process = psutil.Process()

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "system": {
                    "memory_usage_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "cpu_usage_percent": cpu_percent,
                    "disk_usage_percent": round((disk.used / disk.total) * 100, 1),
                    "disk_free_gb": round(disk.free / (1024**3), 2)
                },
                "process": {
                    "memory_mb": round(process.memory_info().rss / (1024 * 1024), 1),
                    "cpu_percent": process.cpu_percent(),
                    "threads": process.num_threads(),
                    "open_files": len(process.open_files())
                }
            }
        except Exception as e:
            self.logger.error(f"📊 Error getting current metrics: {e}")
            return {"error": str(e)}

    def get_performance_summary(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get performance summary for the specified time period"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
            recent_metrics = [m for m in self.metrics_buffer if m.timestamp >= cutoff_time]

            if not recent_metrics:
                return {"message": "No metrics available for the specified period"}

            # Group metrics by type
            metrics_by_type = {}
            for metric in recent_metrics:
                if metric.metric_type not in metrics_by_type:
                    metrics_by_type[metric.metric_type] = []
                metrics_by_type[metric.metric_type].append(metric.value)

            # Calculate statistics
            summary = {
                "period_hours": hours_back,
                "metrics_collected": len(recent_metrics),
                "summary": {}
            }

            for metric_type, values in metrics_by_type.items():
                summary["summary"][metric_type] = {
                    "average": round(sum(values) / len(values), 2),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "count": len(values)
                }

                # Add threshold warnings
                avg_value = summary["summary"][metric_type]["average"]
                threshold_key = metric_type.replace("_time", "_time_ms").replace("_percent", "_percent")

                if threshold_key in self.thresholds and avg_value > self.thresholds[threshold_key]:
                    summary["summary"][metric_type]["warning"] = f"Average exceeds threshold ({self.thresholds[threshold_key]})"

            return summary

        except Exception as e:
            self.logger.error(f"📊 Error generating performance summary: {e}")
            return {"error": str(e)}

    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status"""
        try:
            current_metrics = self.get_current_metrics()

            if "error" in current_metrics:
                return {"status": "error", "details": current_metrics}

            status = "healthy"
            issues = []

            # Check memory
            memory_usage = current_metrics["system"]["memory_usage_percent"]
            if memory_usage > self.thresholds['memory_usage_percent']:
                status = "warning"
                issues.append(f"High memory usage: {memory_usage:.1f}%")

            # Check CPU
            cpu_usage = current_metrics["system"]["cpu_usage_percent"]
            if cpu_usage > self.thresholds['cpu_usage_percent']:
                status = "warning" if status == "healthy" else "critical"
                issues.append(f"High CPU usage: {cpu_usage:.1f}%")

            # Check disk space
            disk_usage = current_metrics["system"]["disk_usage_percent"]
            if disk_usage > 90:
                status = "critical"
                issues.append(f"Low disk space: {disk_usage:.1f}% used")
            elif disk_usage > 80:
                if status == "healthy":
                    status = "warning"
                issues.append(f"Disk space getting low: {disk_usage:.1f}% used")

            return {
                "status": status,
                "issues": issues,
                "metrics": current_metrics,
                "monitoring_active": self.is_monitoring
            }

        except Exception as e:
            self.logger.error(f"📊 Error checking health status: {e}")
            return {"status": "error", "error": str(e)}

    def export_metrics(self, format: str = "json") -> str:
        """Export collected metrics in specified format"""
        try:
            if format.lower() == "json":
                metrics_data = []
                for metric in self.metrics_buffer:
                    metrics_data.append({
                        "timestamp": metric.timestamp.isoformat(),
                        "type": metric.metric_type,
                        "value": metric.value,
                        "unit": metric.unit,
                        "context": metric.context or {}
                    })
                return json.dumps(metrics_data, indent=2)
            else:
                raise ValueError(f"Unsupported format: {format}")

        except Exception as e:
            self.logger.error(f"📊 Error exporting metrics: {e}")
            return json.dumps({"error": str(e)})


class OperationTimer:
    """Context manager for timing operations"""

    def __init__(self, monitor: PerformanceMonitor, operation_name: str):
        self.monitor = monitor
        self.operation_name = operation_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            asyncio.create_task(self._record_timing(duration_ms))

    async def _record_timing(self, duration_ms: float):
        """Record the timing metric"""
        self.monitor._add_metric(PerformanceMetric(
            timestamp=datetime.utcnow(),
            metric_type="operation_time",
            value=duration_ms,
            unit="ms",
            context={"operation": self.operation_name}
        ))


# Global performance monitor instance
performance_monitor = PerformanceMonitor()