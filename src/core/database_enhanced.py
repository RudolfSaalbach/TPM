"""
Production-ready Database service for Chronos Engine v2.1
Enhanced with proper error handling, connection pooling, and monitoring
"""

import asyncio
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy import text, event
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError

from src.core.models import Base


class DatabaseConnectionError(Exception):
    """Database connection specific error"""
    pass


class DatabaseTransactionError(Exception):
    """Database transaction specific error"""
    pass


class DatabaseService:
    """Production-ready async SQLite database service"""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///./data/chronos.db",
                 max_connections: int = 20, pool_timeout: int = 30):
        self.database_url = database_url
        self.max_connections = max_connections
        self.pool_timeout = pool_timeout
        self.logger = logging.getLogger(__name__)
        self._engine = None
        self._SessionLocal = None
        self._lock = threading.Lock()
        self._health_status = {"healthy": True, "last_check": time.time()}

        # Connection metrics
        self._connection_metrics = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "connection_errors": []
        }

    async def initialize(self):
        """Initialize database service with proper error handling"""
        try:
            # Ensure data directory exists with proper permissions
            db_path = Path("./data")
            db_path.mkdir(mode=0o750, exist_ok=True)

            # Validate database file permissions if it exists
            db_file = Path("./data/chronos.db")
            if db_file.exists():
                await self._validate_database_file(db_file)

            # Create async engine with production settings
            await self._create_engine()

            # Initialize database schema
            await self.create_tables()

            # Start background health monitoring
            asyncio.create_task(self._health_monitor())

            self.logger.info("Database service initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize database service: {e}")
            raise DatabaseConnectionError(f"Database initialization failed: {e}")

    async def _create_engine(self):
        """Create database engine with production configuration"""
        # Enhanced SQLite connection arguments
        sqlite_args = {
            "check_same_thread": False,
            "timeout": self.pool_timeout,
            "isolation_level": None,  # Autocommit mode for better control
        }

        # Use QueuePool for better connection management in production
        if "sqlite" in self.database_url:
            pool_class = StaticPool  # SQLite requires StaticPool
            pool_size = 1  # SQLite doesn't support multiple connections well
            max_overflow = 0
        else:
            pool_class = QueuePool
            pool_size = 5
            max_overflow = self.max_connections - pool_size

        self._engine = create_async_engine(
            self.database_url,
            echo=False,  # Never log SQL in production
            poolclass=pool_class,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=3600,  # Recycle connections every hour
            connect_args=sqlite_args
        )

        # Add connection event listeners for monitoring
        @event.listens_for(self._engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            self._connection_metrics["total_connections"] += 1
            self._connection_metrics["active_connections"] += 1

            # Set SQLite pragmas for production
            if "sqlite" in self.database_url:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.close()

        @event.listens_for(self._engine.sync_engine, "close")
        def on_close(dbapi_connection, connection_record):
            self._connection_metrics["active_connections"] = max(0,
                self._connection_metrics["active_connections"] - 1)

        # Create session factory
        self._SessionLocal = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,  # Manual control over flushing
            autocommit=False
        )

    async def _validate_database_file(self, db_file: Path):
        """Validate database file integrity and permissions"""
        try:
            # Check file permissions
            if not db_file.is_file():
                raise DatabaseConnectionError(f"Database file is not a regular file: {db_file}")

            # Check read/write permissions
            if not os.access(db_file, os.R_OK | os.W_OK):
                raise DatabaseConnectionError(f"Insufficient permissions for database file: {db_file}")

            # Basic SQLite integrity check
            import sqlite3
            conn = sqlite3.connect(str(db_file))
            try:
                cursor = conn.execute("PRAGMA integrity_check")
                result = cursor.fetchone()
                if result[0] != "ok":
                    raise DatabaseConnectionError(f"Database integrity check failed: {result[0]}")
            finally:
                conn.close()

        except Exception as e:
            self.logger.error(f"Database file validation failed: {e}")
            raise

    @asynccontextmanager
    async def get_session(self, retry_count: int = 3) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session with retry logic and proper error handling"""
        if not self._SessionLocal:
            raise DatabaseConnectionError("Database service not initialized")

        session = None
        last_exception = None

        for attempt in range(retry_count):
            try:
                session = self._SessionLocal()

                # Test connection
                await session.execute(text("SELECT 1"))

                yield session

                # Commit if no exception occurred
                if session.in_transaction():
                    await session.commit()

                return  # Success, exit retry loop

            except OperationalError as e:
                last_exception = e
                self._connection_metrics["failed_connections"] += 1
                self._log_connection_error(e, attempt + 1)

                if session:
                    try:
                        await session.rollback()
                    except:
                        pass

                if attempt < retry_count - 1:
                    # Exponential backoff
                    await asyncio.sleep(2 ** attempt)

            except IntegrityError as e:
                # Don't retry integrity errors
                last_exception = e
                if session:
                    try:
                        await session.rollback()
                    except:
                        pass
                raise DatabaseTransactionError(f"Data integrity error: {e}")

            except Exception as e:
                last_exception = e
                if session:
                    try:
                        await session.rollback()
                    except:
                        pass
                raise

            finally:
                if session:
                    try:
                        await session.close()
                    except:
                        pass
                    session = None

        # If we get here, all retries failed
        self._health_status["healthy"] = False
        raise DatabaseConnectionError(f"Failed to get database session after {retry_count} attempts: {last_exception}")

    def _log_connection_error(self, error: Exception, attempt: int):
        """Log connection errors with proper context"""
        error_info = {
            "error": str(error),
            "attempt": attempt,
            "timestamp": time.time(),
            "error_type": type(error).__name__
        }

        self._connection_metrics["connection_errors"].append(error_info)

        # Keep only last 10 errors
        if len(self._connection_metrics["connection_errors"]) > 10:
            self._connection_metrics["connection_errors"].pop(0)

        self.logger.warning(f"Database connection error (attempt {attempt}): {error}")

    async def create_tables(self):
        """Create tables with enhanced error handling"""
        self.logger.info("Creating database tables...")

        try:
            async with self._engine.begin() as conn:
                # Import all models
                from src.core.models import (
                    ChronosEventDB, AnalyticsDataDB, TaskDB, TemplateDB,
                    TemplateUsageDB, NoteDB, ExternalCommandDB, URLPayloadDB,
                    EventLinkDB, ActionWorkflowDB
                )
                from src.database.models import PendingSync
                from src.core.security import APIKeyDB, AuditLogDB
                from src.core.outbox import OutboxEntryDB
                from src.core.schema_extensions import (
                    WhitelistDB, WorkflowDB, EmailTemplateDB, WebhookTemplateDB,
                    EmailLogDB, BackupJobDB, BackupHistoryDB, EventModeDB,
                    IntegrationConfigDB, CommandExecutionDB, SystemMetricsDB
                )

                # Enable SQLite optimizations
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
                await conn.execute(text("PRAGMA foreign_keys=ON"))
                await conn.execute(text("PRAGMA busy_timeout=30000"))

                # Create all tables
                await conn.run_sync(Base.metadata.create_all)

                # Verify critical tables exist
                await self._verify_critical_tables(conn)

                self.logger.info("All tables created successfully")

        except Exception as e:
            self.logger.error(f"Error creating tables: {e}")
            raise DatabaseConnectionError(f"Table creation failed: {e}")

    async def _verify_critical_tables(self, conn):
        """Verify that critical tables were created successfully"""
        critical_tables = ['events', 'api_keys', 'audit_log', 'outbox']

        for table in critical_tables:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
                {"table_name": table}
            )
            if not result.fetchone():
                raise DatabaseConnectionError(f"Critical table '{table}' was not created")

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check with detailed metrics"""
        health_info = {
            "healthy": True,
            "timestamp": time.time(),
            "database": {
                "status": "unknown",
                "response_time_ms": None,
                "error": None
            },
            "connections": self._connection_metrics.copy(),
            "tables": {
                "count": 0,
                "error": None
            }
        }

        try:
            # Test database connectivity and response time
            start_time = time.time()

            async with self.get_session() as session:
                # Test basic query
                await session.execute(text("SELECT 1"))

                # Check table count
                result = await session.execute(
                    text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                )
                table_count = result.scalar()
                health_info["tables"]["count"] = table_count

            response_time = (time.time() - start_time) * 1000
            health_info["database"]["response_time_ms"] = response_time
            health_info["database"]["status"] = "healthy"

            # Update health status
            self._health_status["healthy"] = True
            self._health_status["last_check"] = time.time()

        except Exception as e:
            health_info["healthy"] = False
            health_info["database"]["status"] = "unhealthy"
            health_info["database"]["error"] = str(e)
            self._health_status["healthy"] = False

            self.logger.error(f"Database health check failed: {e}")

        return health_info

    async def _health_monitor(self):
        """Background health monitoring task"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self.health_check()
            except Exception as e:
                self.logger.error(f"Health monitor error: {e}")

    async def get_metrics(self) -> Dict[str, Any]:
        """Get detailed database metrics"""
        try:
            async with self.get_session() as session:
                # Get table sizes
                tables_info = {}
                table_names = ['events', 'api_keys', 'audit_log', 'outbox', 'email_templates']

                for table in table_names:
                    try:
                        result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar()
                        tables_info[table] = {"row_count": count}
                    except Exception as e:
                        tables_info[table] = {"error": str(e)}

                # Get database size
                result = await session.execute(text("PRAGMA page_count"))
                page_count = result.scalar()
                result = await session.execute(text("PRAGMA page_size"))
                page_size = result.scalar()
                db_size_bytes = page_count * page_size if page_count and page_size else 0

                return {
                    "connection_metrics": self._connection_metrics,
                    "database_size_bytes": db_size_bytes,
                    "tables": tables_info,
                    "health_status": self._health_status
                }

        except Exception as e:
            self.logger.error(f"Error getting database metrics: {e}")
            return {"error": str(e)}

    async def backup_database(self, backup_path: Path) -> bool:
        """Create a consistent database backup"""
        try:
            import sqlite3

            # Get the database file path
            db_file = Path("./data/chronos.db")
            if not db_file.exists():
                return False

            # Create backup using SQLite backup API
            source = sqlite3.connect(str(db_file))
            backup = sqlite3.connect(str(backup_path))

            try:
                source.backup(backup)
                return True
            finally:
                source.close()
                backup.close()

        except Exception as e:
            self.logger.error(f"Database backup failed: {e}")
            return False

    async def close(self):
        """Properly close database connections"""
        try:
            if self._engine:
                await self._engine.dispose()
                self.logger.info("Database connections closed")
        except Exception as e:
            self.logger.error(f"Error closing database: {e}")


# Global database service instance
db_service = DatabaseService()


# Dependency for FastAPI with proper error handling
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session in FastAPI routes"""
    try:
        async with db_service.get_session() as session:
            yield session
    except DatabaseConnectionError as e:
        # Log error and re-raise as HTTP 503
        logging.getLogger(__name__).error(f"Database connection failed: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except DatabaseTransactionError as e:
        # Log error and re-raise as HTTP 400
        logging.getLogger(__name__).error(f"Database transaction failed: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Database transaction failed")


import os  # Add missing import