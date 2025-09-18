"""
Alembic environment configuration for Chronos Engine v2.1
Handles SQLite database migrations with proper async support
"""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import our models
from src.core.models import Base
from src.config.config_loader import load_config

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def get_database_url():
    """Get database URL from configuration"""
    try:
        chronos_config = load_config()
        db_url = chronos_config.get('database', {}).get('url', 'sqlite+aiosqlite:///./data/chronos.db')
        
        # Convert async URL to sync for migrations
        if 'aiosqlite' in db_url:
            db_url = db_url.replace('sqlite+aiosqlite://', 'sqlite:///')
        
        return db_url
    except Exception:
        # Fallback to default
        return 'sqlite:///./data/chronos.db'


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with given connection"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # Required for SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode"""
    
    # Create data directory if it doesn't exist
    data_dir = Path('./data')
    data_dir.mkdir(exist_ok=True)
    
    url = get_database_url()
    
    # Convert back to async URL for async engine
    if url.startswith('sqlite:///'):
        async_url = url.replace('sqlite:///', 'sqlite+aiosqlite:///')
    else:
        async_url = url
    
    connectable = create_async_engine(
        async_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
