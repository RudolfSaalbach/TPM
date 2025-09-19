"""
Production-ready Logging Manager for Chronos Engine
Structured logging with security, performance monitoring, and error tracking
"""

import logging
import logging.handlers
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import queue
import time
import os


class LogLevel(Enum):
    """Log levels"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class LogCategory(Enum):
    """Log categories for structured logging"""
    SYSTEM = "system"
    SECURITY = "security"
    DATABASE = "database"
    API = "api"
    INTEGRATION = "integration"
    BACKUP = "backup"
    EMAIL = "email"
    PERFORMANCE = "performance"
    AUDIT = "audit"


@dataclass
class LogRecord:
    """Structured log record"""
    timestamp: str
    level: str
    category: str
    message: str
    component: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    error_code: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {k: v for k, v in asdict(self).items() if v is not None}


class SecuritySafeFormatter(logging.Formatter):
    """Formatter that sanitizes sensitive information"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sensitive_fields = {
            'password', 'secret', 'token', 'key', 'authorization',
            'cookie', 'session', 'api_key', 'private_key'
        }

    def format(self, record):
        """Format log record with sensitive data sanitization"""
        # Sanitize the message
        if hasattr(record, 'getMessage'):
            message = record.getMessage()
            record.msg = self._sanitize_message(message)

        # Sanitize any args
        if record.args:
            record.args = tuple(self._sanitize_value(arg) for arg in record.args)

        return super().format(record)

    def _sanitize_message(self, message: str) -> str:
        """Sanitize sensitive information from log message"""
        # Simple pattern-based sanitization
        for field in self.sensitive_fields:
            if field in message.lower():
                # Replace potential sensitive values
                import re
                # Match field=value or field: value patterns
                pattern = rf'{field}["\']?\s*[:=]\s*["\']?([^"\s,}}]+)'
                message = re.sub(pattern, rf'{field}=***', message, flags=re.IGNORECASE)

        return message

    def _sanitize_value(self, value: Any) -> Any:
        """Sanitize sensitive values"""
        if isinstance(value, str):
            return self._sanitize_message(value)
        elif isinstance(value, dict):
            return {k: '***' if any(sens in k.lower() for sens in self.sensitive_fields) else v
                   for k, v in value.items()}
        return value


class StructuredLogger:
    """Structured logger with context management"""

    def __init__(self, component: str):
        self.component = component
        self.logger = logging.getLogger(component)
        self._context = threading.local()

    def set_context(self, **kwargs):
        """Set logging context for current thread"""
        if not hasattr(self._context, 'data'):
            self._context.data = {}
        self._context.data.update(kwargs)

    def clear_context(self):
        """Clear logging context"""
        if hasattr(self._context, 'data'):
            self._context.data.clear()

    def get_context(self) -> Dict[str, Any]:
        """Get current logging context"""
        if hasattr(self._context, 'data'):
            return self._context.data.copy()
        return {}

    def _log(self, level: LogLevel, category: LogCategory, message: str,
            error_code: Optional[str] = None, duration_ms: Optional[float] = None,
            exception: Optional[Exception] = None, **metadata):
        """Internal logging method"""

        context = self.get_context()

        # Create structured log record
        record = LogRecord(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            level=level.name,
            category=category.value,
            message=message,
            component=self.component,
            session_id=context.get('session_id'),
            user_id=context.get('user_id'),
            ip_address=context.get('ip_address'),
            request_id=context.get('request_id'),
            duration_ms=duration_ms,
            error_code=error_code,
            stack_trace=traceback.format_exc() if exception else None,
            metadata={**metadata, **context.get('metadata', {})} if metadata or context.get('metadata') else None
        )

        # Log using standard logger
        extra = {'structured_record': record}

        if exception:
            self.logger.log(level.value, message, exc_info=exception, extra=extra)
        else:
            self.logger.log(level.value, message, extra=extra)

    def debug(self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
        """Log debug message"""
        self._log(LogLevel.DEBUG, category, message, **kwargs)

    def info(self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
        """Log info message"""
        self._log(LogLevel.INFO, category, message, **kwargs)

    def warning(self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
        """Log warning message"""
        self._log(LogLevel.WARNING, category, message, **kwargs)

    def error(self, message: str, category: LogCategory = LogCategory.SYSTEM,
             error_code: Optional[str] = None, exception: Optional[Exception] = None, **kwargs):
        """Log error message"""
        self._log(LogLevel.ERROR, category, message, error_code=error_code, exception=exception, **kwargs)

    def critical(self, message: str, category: LogCategory = LogCategory.SYSTEM,
                error_code: Optional[str] = None, exception: Optional[Exception] = None, **kwargs):
        """Log critical message"""
        self._log(LogLevel.CRITICAL, category, message, error_code=error_code, exception=exception, **kwargs)

    def security_event(self, message: str, event_type: str, risk_level: str = "medium", **kwargs):
        """Log security event"""
        self._log(LogLevel.WARNING, LogCategory.SECURITY, message,
                 error_code=f"SEC_{event_type.upper()}",
                 event_type=event_type, risk_level=risk_level, **kwargs)

    def performance_metric(self, operation: str, duration_ms: float, **kwargs):
        """Log performance metric"""
        self._log(LogLevel.INFO, LogCategory.PERFORMANCE,
                 f"Operation '{operation}' completed in {duration_ms:.2f}ms",
                 duration_ms=duration_ms, operation=operation, **kwargs)

    def api_request(self, method: str, path: str, status_code: int, duration_ms: float, **kwargs):
        """Log API request"""
        level = LogLevel.ERROR if status_code >= 500 else LogLevel.WARNING if status_code >= 400 else LogLevel.INFO
        self._log(level, LogCategory.API,
                 f"{method} {path} - {status_code}",
                 duration_ms=duration_ms, method=method, path=path, status_code=status_code, **kwargs)

    def database_operation(self, operation: str, table: str, duration_ms: float, rows_affected: int = 0, **kwargs):
        """Log database operation"""
        self._log(LogLevel.DEBUG, LogCategory.DATABASE,
                 f"Database {operation} on {table} - {rows_affected} rows affected",
                 duration_ms=duration_ms, operation=operation, table=table, rows_affected=rows_affected, **kwargs)


class JSONFormatter(SecuritySafeFormatter):
    """JSON formatter for structured logging"""

    def format(self, record):
        """Format record as JSON"""
        # Get structured record if available
        structured_record = getattr(record, 'structured_record', None)

        if structured_record:
            log_data = structured_record.to_dict()
        else:
            # Fallback to standard record
            log_data = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat() + 'Z',
                'level': record.levelname,
                'category': 'system',
                'message': self._sanitize_message(record.getMessage()),
                'component': record.name,
                'metadata': {
                    'filename': record.filename,
                    'lineno': record.lineno,
                    'funcName': record.funcName
                }
            }

        # Add exception info if present
        if record.exc_info:
            log_data['stack_trace'] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class AsyncFileHandler(logging.handlers.RotatingFileHandler):
    """Asynchronous file handler for high-performance logging"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._queue = queue.Queue(maxsize=10000)
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._stop_event = threading.Event()
        self._worker_thread.start()

    def emit(self, record):
        """Emit log record asynchronously"""
        try:
            if not self._stop_event.is_set():
                self._queue.put_nowait(record)
        except queue.Full:
            # Drop log if queue is full to prevent blocking
            pass

    def _worker(self):
        """Background worker thread for writing logs"""
        while not self._stop_event.is_set():
            try:
                record = self._queue.get(timeout=1.0)
                super().emit(record)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                # Avoid recursive logging
                print(f"Logging error: {e}", file=sys.stderr)

    def close(self):
        """Close handler and stop worker thread"""
        self._stop_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
        super().close()


class LoggingManager:
    """Main logging manager for the application"""

    def __init__(self):
        self.configured = False
        self.handlers = []
        self.loggers = {}

    def configure(self, config):
        """Configure logging system"""
        if self.configured:
            return

        try:
            # Create logs directory
            log_dir = Path(config.logging.file_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)

            # Set root logger level
            root_logger = logging.getLogger()
            root_logger.setLevel(getattr(logging, config.logging.level.upper()))

            # Clear existing handlers
            root_logger.handlers.clear()

            # Console handler
            if config.logging.console_enabled:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(getattr(logging, config.logging.level.upper()))

                if config.environment.value == 'development':
                    # Human-readable format for development
                    console_formatter = SecuritySafeFormatter(
                        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                    )
                else:
                    # JSON format for production
                    console_formatter = JSONFormatter()

                console_handler.setFormatter(console_formatter)
                root_logger.addHandler(console_handler)
                self.handlers.append(console_handler)

            # File handler
            if config.logging.file_enabled:
                file_handler = AsyncFileHandler(
                    filename=config.logging.file_path,
                    maxBytes=config.logging.file_max_size,
                    backupCount=config.logging.file_backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(getattr(logging, config.logging.level.upper()))
                file_formatter = JSONFormatter()
                file_handler.setFormatter(file_formatter)
                root_logger.addHandler(file_handler)
                self.handlers.append(file_handler)

            # Security log handler (separate file for security events)
            security_handler = AsyncFileHandler(
                filename=str(log_dir / 'security.log'),
                maxBytes=config.logging.file_max_size,
                backupCount=config.logging.file_backup_count,
                encoding='utf-8'
            )
            security_handler.setLevel(logging.WARNING)
            security_handler.addFilter(lambda record: getattr(record, 'structured_record', None) and
                                     getattr(record.structured_record, 'category', None) == 'security')
            security_handler.setFormatter(JSONFormatter())
            root_logger.addHandler(security_handler)
            self.handlers.append(security_handler)

            # Performance log handler
            performance_handler = AsyncFileHandler(
                filename=str(log_dir / 'performance.log'),
                maxBytes=config.logging.file_max_size,
                backupCount=config.logging.file_backup_count,
                encoding='utf-8'
            )
            performance_handler.setLevel(logging.INFO)
            performance_handler.addFilter(lambda record: getattr(record, 'structured_record', None) and
                                        getattr(record.structured_record, 'category', None) == 'performance')
            performance_handler.setFormatter(JSONFormatter())
            root_logger.addHandler(performance_handler)
            self.handlers.append(performance_handler)

            # Set file permissions
            for handler in self.handlers:
                if hasattr(handler, 'baseFilename'):
                    try:
                        os.chmod(handler.baseFilename, 0o640)
                    except (OSError, AttributeError):
                        pass

            self.configured = True

            # Log successful configuration
            logger = self.get_logger('logging_manager')
            logger.info("Logging system configured successfully", category=LogCategory.SYSTEM)

        except Exception as e:
            print(f"Failed to configure logging: {e}", file=sys.stderr)
            raise

    def get_logger(self, component: str) -> StructuredLogger:
        """Get structured logger for component"""
        if component not in self.loggers:
            self.loggers[component] = StructuredLogger(component)
        return self.loggers[component]

    def shutdown(self):
        """Shutdown logging system"""
        for handler in self.handlers:
            try:
                handler.close()
            except Exception as e:
                print(f"Error closing log handler: {e}", file=sys.stderr)

        self.handlers.clear()
        self.loggers.clear()
        self.configured = False


# Global logging manager
logging_manager = LoggingManager()


def get_logger(component: str) -> StructuredLogger:
    """Get logger for component"""
    return logging_manager.get_logger(component)


# Context managers for logging
class LoggingContext:
    """Context manager for logging context"""

    def __init__(self, logger: StructuredLogger, **context):
        self.logger = logger
        self.context = context
        self.original_context = None

    def __enter__(self):
        self.original_context = self.logger.get_context()
        self.logger.set_context(**self.context)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.clear_context()
        if self.original_context:
            self.logger.set_context(**self.original_context)


class PerformanceTimer:
    """Context manager for performance timing"""

    def __init__(self, logger: StructuredLogger, operation: str, **kwargs):
        self.logger = logger
        self.operation = operation
        self.kwargs = kwargs
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            if exc_type:
                self.logger.error(f"Operation '{self.operation}' failed after {duration_ms:.2f}ms",
                                category=LogCategory.PERFORMANCE, duration_ms=duration_ms,
                                operation=self.operation, exception=exc_val, **self.kwargs)
            else:
                self.logger.performance_metric(self.operation, duration_ms, **self.kwargs)