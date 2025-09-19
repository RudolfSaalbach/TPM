"""
Enhanced Database service for Chronos Engine v2.1
SQLite database management with Alembic migrations
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

from src.core.models import Base


class DatabaseService:
    """Enhanced async SQLite database service with migrations"""
    
    def __init__(self, database_url: str = "sqlite+aiosqlite:///./data/chronos.db"):
        self.database_url = database_url
        self.logger = logging.getLogger(__name__)
        
        # Ensure data directory exists
        db_path = Path("./data")
        db_path.mkdir(exist_ok=True)
        
        # Create async engine
        self.engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
        
        # Create session factory
        self.SessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        self.logger.info(f"Enhanced Database service initialized: {database_url}")
    
    async def initialize_database(self):
        """Initialize database with migrations"""
        try:
            self.logger.info("Initializing database...")
            
            # Check if database exists and has tables
            needs_migration = await self._needs_initial_migration()
            
            if needs_migration:
                self.logger.info("Database is empty, running initial migration...")
                await self._run_alembic_upgrade()
            else:
                self.logger.info("Database exists, checking for pending migrations...")
                await self._check_and_run_migrations()
            
            # Verify database health
            if await self.health_check():
                self.logger.info("Database initialization completed successfully")
            else:
                raise Exception("Database health check failed after initialization")
                
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _needs_initial_migration(self) -> bool:
        """Check if database needs initial migration"""
        try:
            async with self.get_session() as session:
                result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='events'"))
                tables = result.fetchall()
                return len(tables) == 0
        except Exception:
            return True
    
    async def _run_alembic_upgrade(self):
        """Run Alembic upgrade to latest version"""
        try:
            self.logger.info("Running Alembic migrations...")

            # Skip Alembic for now due to aiosqlite compatibility issues
            # Database tables are created properly by SQLAlchemy directly
            self.logger.info("Skipping Alembic migrations - using direct SQLAlchemy table creation")

            # Create tables directly using SQLAlchemy
            await self._create_tables_directly()
            return

            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                self.logger.error(f"Alembic upgrade failed: {result.stderr}")
                raise Exception(f"Migration failed: {result.stderr}")

            self.logger.info("Alembic migrations completed successfully")

        except subprocess.TimeoutExpired:
            self.logger.error("Alembic migration timed out")
            raise Exception("Migration timed out")
        except Exception as e:
            self.logger.error(f"Alembic migration error: {e}")
            raise
    
    async def _check_and_run_migrations(self):
        """Check for and run pending migrations"""
        try:
            # Check current revision
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "current"],
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                current_rev = result.stdout.strip()
                self.logger.debug(f"Current database revision: {current_rev}")
                
                # Check if we're at head
                head_result = subprocess.run(
                    [sys.executable, "-m", "alembic", "heads"],
                    cwd=Path.cwd(),
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if head_result.returncode == 0:
                    head_rev = head_result.stdout.strip()
                    
                    if current_rev != head_rev and head_rev:
                        self.logger.info("Pending migrations found, upgrading...")
                        await self._run_alembic_upgrade()
                    else:
                        self.logger.info("Database is up to date")
                else:
                    self.logger.warning("Could not check head revision, running upgrade...")
                    await self._run_alembic_upgrade()
            else:
                self.logger.warning("Could not check current revision, running upgrade...")
                await self._run_alembic_upgrade()
                
        except Exception as e:
            self.logger.error(f"Migration check failed: {e}")
            # Don't raise here - try to continue with existing database

    async def _create_tables_directly(self):
        """Create tables directly using SQLAlchemy without Alembic"""
        try:
            async with self.engine.begin() as conn:
                # Import all models to ensure they're registered
                from src.core.models import ChronosEventDB, AnalyticsDataDB, TaskDB, TemplateDB, TemplateUsageDB, NoteDB, ExternalCommandDB, URLPayloadDB, EventLinkDB, ActionWorkflowDB
                from src.database.models import PendingSync

                # Create all tables defined in Base.metadata
                await conn.run_sync(Base.metadata.create_all)
                self.logger.info("All tables created successfully using direct SQLAlchemy")

        except Exception as e:
            self.logger.error(f"Error creating tables directly: {e}")
            raise
    
    async def create_tables(self):
        """Create tables using SQLAlchemy directly"""
        self.logger.info("Creating tables using SQLAlchemy...")
        try:
            async with self.engine.begin() as conn:
                # Import all models to ensure they're registered
                from src.core.models import ChronosEventDB, AnalyticsDataDB, TaskDB, TemplateDB, TemplateUsageDB, NoteDB, ExternalCommandDB, URLPayloadDB, EventLinkDB, ActionWorkflowDB
                from src.database.models import PendingSync

                # Create all tables
                await conn.run_sync(Base.metadata.create_all)
                self.logger.info("All tables created successfully")

        except Exception as e:
            self.logger.error(f"Error creating tables: {e}")
            raise
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session"""
        async with self.SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def health_check(self) -> bool:
        """Check database connection health"""
        try:
            async with self.get_session() as session:
                await session.execute(text("SELECT 1"))
                
                # Check if main tables exist
                result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('events', 'tasks', 'analytics_data')")
                )
                tables = result.fetchall()
                
                if len(tables) < 3:
                    self.logger.warning(f"Only {len(tables)}/3 expected tables found")
                    return False
                
                return True
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False
    
    async def get_schema_info(self) -> dict:
        """Get database schema information"""
        try:
            async with self.get_session() as session:
                # Get table list
                tables_result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                )
                tables = [row[0] for row in tables_result.fetchall()]
                
                # Get current Alembic revision
                try:
                    rev_result = await session.execute(
                        text("SELECT version_num FROM alembic_version LIMIT 1")
                    )
                    current_revision = rev_result.scalar()
                except:
                    current_revision = None
                
                return {
                    'tables': tables,
                    'table_count': len(tables),
                    'current_revision': current_revision,
                    'database_file': self.database_url
                }
        except Exception as e:
            self.logger.error(f"Failed to get schema info: {e}")
            return {'error': str(e)}
    
    async def close(self):
        """Close database connections"""
        await self.engine.dispose()
        self.logger.info("Database connections closed")


# Global database service instance
db_service = DatabaseService()


# Dependency for FastAPI
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session in FastAPI routes"""
    async with db_service.get_session() as session:
        yield session
