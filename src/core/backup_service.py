"""
Backup service for Chronos Engine - Simple and reliable backups
Creates ZIP archives with database, config, and assets
"""

import asyncio
import hashlib
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import json
import sqlite3
import os

from src.core.schema_extensions import BackupJobDB, BackupHistoryDB


@dataclass
class BackupConfig:
    """Backup configuration"""
    name: str = "default"
    include_database: bool = True
    include_config: bool = True
    include_templates: bool = True
    include_logs: bool = False
    exclude_patterns: List[str] = field(default_factory=lambda: ["*.tmp", "*.lock", "__pycache__"])
    compression_level: int = 6
    max_backup_size_mb: int = 1000


@dataclass
class BackupResult:
    """Backup operation result"""
    success: bool
    backup_filename: str
    backup_size_bytes: int
    checksum: str
    duration_seconds: float
    error_message: Optional[str] = None
    files_included: List[str] = field(default_factory=list)


class BackupService:
    """Service for creating and managing backups"""

    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(exist_ok=True)

    async def create_backup(self, config: BackupConfig = None,
                           description: str = "") -> BackupResult:
        """Create a new backup"""
        if config is None:
            config = BackupConfig()

        start_time = datetime.now()

        try:
            # Generate backup filename
            timestamp = start_time.strftime("%Y%m%d_%H%M%S")
            backup_filename = f"chronos_backup_{timestamp}.zip"
            backup_path = self.backup_dir / backup_filename

            # Create backup
            files_included = await self._create_backup_archive(backup_path, config)

            # Calculate checksum and size
            checksum = await self._calculate_checksum(backup_path)
            backup_size = backup_path.stat().st_size

            duration = (datetime.now() - start_time).total_seconds()

            result = BackupResult(
                success=True,
                backup_filename=backup_filename,
                backup_size_bytes=backup_size,
                checksum=checksum,
                duration_seconds=duration,
                files_included=files_included
            )

            # Log to database
            if self.db_session_factory:
                await self._log_backup(result, config, description)

            return result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return BackupResult(
                success=False,
                backup_filename="",
                backup_size_bytes=0,
                checksum="",
                duration_seconds=duration,
                error_message=str(e)
            )

    async def _create_backup_archive(self, backup_path: Path,
                                   config: BackupConfig) -> List[str]:
        """Create the backup ZIP archive"""
        files_included = []

        def add_file_to_zip(zip_file, file_path: Path, archive_name: str):
            """Add file to ZIP with error handling"""
            try:
                if file_path.exists() and file_path.is_file():
                    zip_file.write(file_path, archive_name)
                    files_included.append(archive_name)
            except Exception as e:
                print(f"Warning: Could not backup {file_path}: {e}")

        def add_directory_to_zip(zip_file, dir_path: Path, archive_prefix: str = ""):
            """Add directory contents to ZIP"""
            if not dir_path.exists():
                return

            for item in dir_path.rglob("*"):
                if item.is_file():
                    # Check exclude patterns
                    if any(item.match(pattern) for pattern in config.exclude_patterns):
                        continue

                    relative_path = item.relative_to(dir_path)
                    archive_name = f"{archive_prefix}/{relative_path}" if archive_prefix else str(relative_path)
                    add_file_to_zip(zip_file, item, archive_name)

        # Run backup creation in thread pool to avoid blocking
        return await asyncio.to_thread(self._create_zip_sync, backup_path, config, files_included)

    def _create_zip_sync(self, backup_path: Path, config: BackupConfig,
                        files_included: List[str]) -> List[str]:
        """Synchronous ZIP creation"""
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED,
                           compresslevel=config.compression_level) as zip_file:

            # Add database
            if config.include_database:
                db_path = Path("data/chronos.db")
                if db_path.exists():
                    # Create a copy to ensure consistency
                    temp_db = Path("data/chronos_backup_temp.db")
                    try:
                        # Use SQLite backup API for safe backup
                        self._backup_database(db_path, temp_db)
                        zip_file.write(temp_db, "data/chronos.db")
                        files_included.append("data/chronos.db")

                        # Also backup WAL file if exists
                        wal_path = Path("data/chronos.db-wal")
                        if wal_path.exists():
                            zip_file.write(wal_path, "data/chronos.db-wal")
                            files_included.append("data/chronos.db-wal")

                    finally:
                        if temp_db.exists():
                            temp_db.unlink()

            # Add configuration files
            if config.include_config:
                config_files = [
                    "chronos.yaml",
                    "config/chronos.yaml",
                    "data/signature_secret.key"
                ]
                for config_file in config_files:
                    config_path = Path(config_file)
                    if config_path.exists():
                        zip_file.write(config_path, config_file)
                        files_included.append(config_file)

            # Add templates directory
            if config.include_templates:
                templates_dir = Path("templates")
                if templates_dir.exists():
                    for template_file in templates_dir.rglob("*"):
                        if template_file.is_file():
                            relative_path = template_file.relative_to(Path("."))
                            zip_file.write(template_file, str(relative_path))
                            files_included.append(str(relative_path))

            # Add static files
            static_dir = Path("static")
            if static_dir.exists():
                for static_file in static_dir.rglob("*"):
                    if static_file.is_file():
                        relative_path = static_file.relative_to(Path("."))
                        zip_file.write(static_file, str(relative_path))
                        files_included.append(str(relative_path))

            # Add logs if requested
            if config.include_logs:
                logs_dir = Path("logs")
                if logs_dir.exists():
                    for log_file in logs_dir.glob("*.log"):
                        relative_path = log_file.relative_to(Path("."))
                        zip_file.write(log_file, str(relative_path))
                        files_included.append(str(relative_path))

            # Add backup metadata
            metadata = {
                "backup_created": datetime.now().isoformat(),
                "chronos_version": "2.1.0",
                "backup_config": {
                    "name": config.name,
                    "include_database": config.include_database,
                    "include_config": config.include_config,
                    "include_templates": config.include_templates,
                    "include_logs": config.include_logs
                },
                "files_included": files_included
            }

            # Add metadata.json
            zip_file.writestr("backup_metadata.json", json.dumps(metadata, indent=2))
            files_included.append("backup_metadata.json")

            # Add restore instructions
            restore_instructions = self._get_restore_instructions()
            zip_file.writestr("RESTORE_INSTRUCTIONS.txt", restore_instructions)
            files_included.append("RESTORE_INSTRUCTIONS.txt")

        return files_included

    def _backup_database(self, source_db: Path, target_db: Path):
        """Safely backup SQLite database using SQLite backup API"""
        try:
            # Connect to source database
            source_conn = sqlite3.connect(str(source_db))

            # Connect to target database
            target_conn = sqlite3.connect(str(target_db))

            # Perform backup
            source_conn.backup(target_conn)

            # Close connections
            source_conn.close()
            target_conn.close()

        except Exception as e:
            # Fallback to file copy if backup API fails
            shutil.copy2(source_db, target_db)

    async def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        def calc_hash():
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()

        return await asyncio.to_thread(calc_hash)

    async def _log_backup(self, result: BackupResult, config: BackupConfig,
                         description: str):
        """Log backup to database"""
        if not self.db_session_factory:
            return

        try:
            history_entry = BackupHistoryDB(
                backup_filename=result.backup_filename,
                backup_size_bytes=result.backup_size_bytes,
                backup_type="manual",
                status="completed" if result.success else "failed",
                error_message=result.error_message,
                started_at=datetime.now() - timedelta(seconds=result.duration_seconds),
                completed_at=datetime.now(),
                checksum=result.checksum
            )

            async with self.db_session_factory() as session:
                session.add(history_entry)
                await session.commit()

        except Exception as e:
            print(f"Warning: Could not log backup to database: {e}")

    def _get_restore_instructions(self) -> str:
        """Generate restore instructions"""
        return """
CHRONOS ENGINE BACKUP RESTORE INSTRUCTIONS
==========================================

This backup contains your Chronos Engine data and configuration.

RESTORE STEPS:
1. Stop the Chronos Engine application
2. Create a new directory for the restored installation
3. Extract this ZIP file into that directory
4. If you have a running Chronos instance:
   - Backup your current data directory
   - Stop the application
   - Replace the data/chronos.db file with the one from this backup
   - Replace configuration files if needed
5. Start Chronos Engine

WHAT'S INCLUDED:
- SQLite database (data/chronos.db)
- Configuration files (chronos.yaml, etc.)
- Templates directory
- Static assets
- Backup metadata

VERIFICATION:
- Check the backup_metadata.json file for details about what was backed up
- Verify the database integrity after restore
- Check that all your events and configurations are present

SUPPORT:
If you encounter issues during restore, check the application logs and
ensure all file permissions are correct.

Backup created: {timestamp}
Version: Chronos Engine 2.1.0
        """.strip().format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    async def list_backups(self) -> List[Dict[str, Any]]:
        """List available backup files"""
        backups = []

        # Get files from backup directory
        for backup_file in self.backup_dir.glob("chronos_backup_*.zip"):
            try:
                stat = backup_file.stat()
                backup_info = {
                    "filename": backup_file.name,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime),
                    "path": str(backup_file)
                }

                # Try to read metadata from ZIP
                try:
                    with zipfile.ZipFile(backup_file, 'r') as zip_file:
                        if "backup_metadata.json" in zip_file.namelist():
                            metadata_content = zip_file.read("backup_metadata.json")
                            metadata = json.loads(metadata_content)
                            backup_info["metadata"] = metadata
                except:
                    pass

                backups.append(backup_info)

            except Exception as e:
                print(f"Warning: Could not read backup {backup_file}: {e}")

        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x["created_at"], reverse=True)

        return backups

    async def delete_backup(self, filename: str) -> bool:
        """Delete a backup file"""
        try:
            backup_path = self.backup_dir / filename
            if backup_path.exists() and backup_path.name.startswith("chronos_backup_"):
                backup_path.unlink()
                return True
            return False
        except Exception:
            return False

    async def cleanup_old_backups(self, keep_count: int = 10,
                                 keep_days: int = 30) -> int:
        """Clean up old backup files"""
        backups = await self.list_backups()
        deleted_count = 0

        # Keep most recent backups
        backups_to_check = backups[keep_count:]

        cutoff_date = datetime.now() - timedelta(days=keep_days)

        for backup in backups_to_check:
            if backup["created_at"] < cutoff_date:
                if await self.delete_backup(backup["filename"]):
                    deleted_count += 1

        return deleted_count

    async def get_backup_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get backup history from database"""
        if not self.db_session_factory:
            return []

        try:
            from sqlalchemy import select

            async with self.db_session_factory() as session:
                result = await session.execute(
                    select(BackupHistoryDB)
                    .order_by(BackupHistoryDB.started_at.desc())
                    .limit(limit)
                )
                history = result.scalars().all()

                return [
                    {
                        "id": entry.id,
                        "filename": entry.backup_filename,
                        "size_bytes": entry.backup_size_bytes,
                        "type": entry.backup_type,
                        "status": entry.status,
                        "started_at": entry.started_at,
                        "completed_at": entry.completed_at,
                        "checksum": entry.checksum,
                        "error_message": entry.error_message
                    }
                    for entry in history
                ]

        except Exception as e:
            print(f"Warning: Could not get backup history: {e}")
            return []


# Scheduled backup job runner
class BackupScheduler:
    """Scheduler for automated backups"""

    def __init__(self, backup_service: BackupService, db_session_factory=None):
        self.backup_service = backup_service
        self.db_session_factory = db_session_factory
        self._running = False

    async def start(self):
        """Start the backup scheduler"""
        if self._running:
            return

        self._running = True
        asyncio.create_task(self._schedule_loop())

    async def stop(self):
        """Stop the backup scheduler"""
        self._running = False

    async def _schedule_loop(self):
        """Main scheduling loop"""
        while self._running:
            try:
                await self._check_and_run_scheduled_backups()
            except Exception as e:
                print(f"Backup scheduler error: {e}")

            # Check every hour
            await asyncio.sleep(3600)

    async def _check_and_run_scheduled_backups(self):
        """Check for and run scheduled backups"""
        if not self.db_session_factory:
            return

        # This would check for scheduled backup jobs and run them
        # For now, just run a daily backup if none exists
        backups = await self.backup_service.list_backups()

        # If no backup today, create one
        today = datetime.now().date()
        has_backup_today = any(
            backup["created_at"].date() == today
            for backup in backups
        )

        if not has_backup_today:
            config = BackupConfig(name="scheduled_daily")
            result = await self.backup_service.create_backup(
                config, "Scheduled daily backup"
            )
            if result.success:
                print(f"Scheduled backup created: {result.backup_filename}")
            else:
                print(f"Scheduled backup failed: {result.error_message}")


# Global backup service instance
backup_service = BackupService()