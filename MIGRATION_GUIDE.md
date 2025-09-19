# Chronos Engine v2.2 - Migration and Rollback Guide

## Overview

This guide provides detailed procedures for migrating to Chronos Engine v2.2, including database migrations, configuration updates, and rollback procedures. It covers both automated and manual migration scenarios.

## Pre-Migration Requirements

### System Compatibility Check

```bash
# Check Python version (3.9+ required)
python --version

# Check SQLite version (3.35+ for JSON support)
python -c "import sqlite3; print(f'SQLite: {sqlite3.sqlite_version}')"

# Check existing database version
python -c "
import sqlite3
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()
try:
    cursor.execute('SELECT version FROM alembic_version')
    print(f'Current DB version: {cursor.fetchone()[0]}')
except:
    print('No migration history found (pre-v2.2)')
conn.close()
"

# Check available disk space (minimum 1GB recommended)
df -h ./data/
```

### Backup Current Installation

```bash
#!/bin/bash
# create_backup.sh - Comprehensive backup script

BACKUP_DIR="./backups/pre_v22_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "Creating pre-v2.2 backup in $BACKUP_DIR"

# Backup database
echo "Backing up database..."
cp ./data/chronos.db "$BACKUP_DIR/chronos.db.backup"

# Backup configuration
echo "Backing up configuration..."
cp chronos.yaml "$BACKUP_DIR/chronos.yaml.backup"

# Backup custom plugins
echo "Backing up custom plugins..."
if [ -d "plugins/custom" ]; then
    tar -czf "$BACKUP_DIR/custom_plugins.tar.gz" plugins/custom/
fi

# Backup logs (recent only)
echo "Backing up recent logs..."
if [ -d "logs" ]; then
    find logs/ -name "*.log" -mtime -7 -exec cp {} "$BACKUP_DIR/" \;
fi

# Create backup manifest
echo "Creating backup manifest..."
cat > "$BACKUP_DIR/backup_manifest.txt" <<EOF
Chronos Engine Pre-v2.2 Backup
Created: $(date)
Database: chronos.db.backup
Configuration: chronos.yaml.backup
Plugins: custom_plugins.tar.gz
Logs: *.log (last 7 days)

Database size: $(ls -lh "$BACKUP_DIR/chronos.db.backup" | awk '{print $5}')
EOF

echo "Backup completed: $BACKUP_DIR"
echo "Backup size: $(du -sh "$BACKUP_DIR" | cut -f1)"
```

## Migration Procedures

### Automated Migration (Recommended)

#### 1. Migration Script

```bash
#!/bin/bash
# migrate_to_v22.sh - Automated migration script

set -e  # Exit on any error

echo "=== Chronos Engine v2.2 Migration Script ==="
echo

# Configuration
BACKUP_DIR="./backups/auto_migration_$(date +%Y%m%d_%H%M%S)"
LOG_FILE="./logs/migration_v22.log"

# Create migration log
mkdir -p logs
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

echo "Migration started at $(date)"
echo "Log file: $LOG_FILE"
echo

# Step 1: Create backup
echo "Step 1: Creating backup..."
mkdir -p "$BACKUP_DIR"
cp ./data/chronos.db "$BACKUP_DIR/"
cp chronos.yaml "$BACKUP_DIR/"
echo "Backup created: $BACKUP_DIR"

# Step 2: Check current state
echo "Step 2: Checking current state..."
python -c "
import sqlite3
import sys
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# Check if we're already on v2.2
try:
    cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"event_links\"')
    if cursor.fetchone():
        print('ERROR: Database already appears to be v2.2')
        sys.exit(1)
except Exception as e:
    print(f'Database check failed: {e}')
    sys.exit(1)

# Check for data integrity
cursor.execute('SELECT COUNT(*) FROM events')
event_count = cursor.fetchone()[0]
print(f'Found {event_count} events in database')

conn.close()
"

if [ $? -ne 0 ]; then
    echo "Pre-migration check failed. Aborting."
    exit 1
fi

# Step 3: Install v2.2 dependencies
echo "Step 3: Installing v2.2 dependencies..."
pip install -r requirements.txt --upgrade

# Step 4: Update configuration
echo "Step 4: Updating configuration..."
if [ ! -f "chronos_v22.yaml" ]; then
    echo "ERROR: chronos_v22.yaml template not found"
    exit 1
fi

# Backup current config and use v2.2 template
cp chronos.yaml "$BACKUP_DIR/chronos_original.yaml"

# Merge existing config with v2.2 template (preserve API keys, etc.)
python -c "
import yaml
import sys

# Load existing config
try:
    with open('chronos.yaml', 'r') as f:
        old_config = yaml.safe_load(f)
except:
    old_config = {}

# Load v2.2 template
with open('chronos_v22.yaml', 'r') as f:
    new_config = yaml.safe_load(f)

# Preserve critical settings
preserve_keys = ['api.api_key', 'database.url', 'timezone']

for key_path in preserve_keys:
    keys = key_path.split('.')
    old_val = old_config
    new_val = new_config

    # Navigate to the nested value in old config
    try:
        for k in keys:
            old_val = old_val[k]

        # Set in new config
        for k in keys[:-1]:
            new_val = new_val[k]
        new_val[keys[-1]] = old_val
        print(f'Preserved {key_path}: {old_val}')
    except:
        print(f'Could not preserve {key_path} (not found in old config)')

# Write merged config
with open('chronos.yaml', 'w') as f:
    yaml.dump(new_config, f, default_flow_style=False)

print('Configuration updated successfully')
"

# Step 5: Run database migration
echo "Step 5: Running database migration..."
python -m alembic upgrade head

if [ $? -ne 0 ]; then
    echo "Database migration failed. Rolling back..."
    cp "$BACKUP_DIR/chronos.db" ./data/
    cp "$BACKUP_DIR/chronos.yaml" ./
    echo "Rollback completed. Check logs for errors."
    exit 1
fi

# Step 6: Verify migration
echo "Step 6: Verifying migration..."
python -c "
import sqlite3
import sys

conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# Check that new tables exist
required_tables = ['event_links', 'action_workflows']
for table in required_tables:
    cursor.execute(f'SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"{table}\"')
    if not cursor.fetchone():
        print(f'ERROR: Table {table} not found after migration')
        sys.exit(1)
    print(f'✓ Table {table} exists')

# Check that sub_tasks column exists
cursor.execute('PRAGMA table_info(events)')
columns = [row[1] for row in cursor.fetchall()]
if 'sub_tasks' not in columns:
    print('ERROR: sub_tasks column not found in events table')
    sys.exit(1)
print('✓ sub_tasks column exists')

# Check data integrity
cursor.execute('SELECT COUNT(*) FROM events')
event_count = cursor.fetchone()[0]
print(f'✓ {event_count} events preserved')

conn.close()
print('Database migration verified successfully')
"

if [ $? -ne 0 ]; then
    echo "Migration verification failed. Check database state."
    exit 1
fi

# Step 7: Test v2.2 features
echo "Step 7: Testing v2.2 features..."
python integration_test.py

if [ $? -ne 0 ]; then
    echo "WARNING: Integration tests failed. Check functionality."
    echo "Migration completed but system may have issues."
    exit 1
fi

echo
echo "=== Migration Completed Successfully ==="
echo "• Database migrated to v2.2 schema"
echo "• Configuration updated with v2.2 features"
echo "• All tests passed"
echo "• Backup available at: $BACKUP_DIR"
echo "• Migration log: $LOG_FILE"
echo
echo "You can now start using v2.2 features!"
```

### Manual Migration Steps

#### 1. Manual Database Migration

```bash
# Step 1: Check current database state
python -c "
import sqlite3
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

print('Current tables:')
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
for row in cursor.fetchall():
    print(f'  - {row[0]}')

print('\nEvents table schema:')
cursor.execute('PRAGMA table_info(events)')
for row in cursor.fetchall():
    print(f'  {row[1]} ({row[2]})')

conn.close()
"

# Step 2: Initialize Alembic (if not already done)
if [ ! -d "alembic" ]; then
    python -m alembic init alembic
    # Update alembic.ini with your database URL
    sed -i 's|sqlalchemy.url = .*|sqlalchemy.url = sqlite:///./data/chronos.db|' alembic.ini
fi

# Step 3: Check migration status
python -m alembic current
python -m alembic heads

# Step 4: Run the v2.2 migration
python -m alembic upgrade head

# Step 5: Verify the migration
python -c "
import sqlite3
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# Verify new tables
new_tables = ['event_links', 'action_workflows']
for table in new_tables:
    cursor.execute(f'SELECT sql FROM sqlite_master WHERE name=\"{table}\"')
    result = cursor.fetchone()
    if result:
        print(f'✓ {table} table created')
        print(f'  Schema: {result[0][:100]}...')
    else:
        print(f'✗ {table} table missing')

# Verify new columns
cursor.execute('PRAGMA table_info(events)')
columns = {row[1]: row[2] for row in cursor.fetchall()}
if 'sub_tasks' in columns:
    print(f'✓ sub_tasks column added ({columns[\"sub_tasks\"]})')
else:
    print('✗ sub_tasks column missing')

conn.close()
"
```

#### 2. Manual Configuration Migration

```bash
# Step 1: Create v2.2 configuration from template
cp chronos_v22.yaml chronos_new.yaml

# Step 2: Extract settings from current config
python -c "
import yaml

# Load current config
with open('chronos.yaml', 'r') as f:
    current = yaml.safe_load(f)

# Load new template
with open('chronos_new.yaml', 'r') as f:
    new = yaml.safe_load(f)

# Extract important settings to preserve
preserve = {
    'api_key': current.get('api', {}).get('api_key'),
    'db_url': current.get('database', {}).get('url'),
    'timezone': current.get('timezone'),
    'debug': current.get('debug'),
}

print('Settings to preserve:')
for key, value in preserve.items():
    if value is not None:
        print(f'  {key}: {value}')

# You'll need to manually merge these into chronos_new.yaml
"

# Step 3: Manually edit chronos_new.yaml to include your settings
echo "Please edit chronos_new.yaml with your specific settings:"
echo "  - API key"
echo "  - Database URL"
echo "  - Debug settings"
echo "  - Command whitelist"
echo "  - Any custom configurations"

read -p "Press Enter when ready to continue..."

# Step 4: Replace old configuration
cp chronos.yaml chronos_old.yaml.backup
cp chronos_new.yaml chronos.yaml

echo "Configuration updated. Backup saved as chronos_old.yaml.backup"
```

### Database-Specific Migrations

#### SQLite to PostgreSQL Migration

```bash
#!/bin/bash
# migrate_sqlite_to_postgres.sh

echo "Migrating from SQLite to PostgreSQL..."

# Step 1: Export data from SQLite
python -c "
import sqlite3
import json
from datetime import datetime

# Connect to SQLite
sqlite_conn = sqlite3.connect('./data/chronos.db')
sqlite_conn.row_factory = sqlite3.Row

# Export events
cursor = sqlite_conn.cursor()
cursor.execute('SELECT * FROM events')
events = [dict(row) for row in cursor.fetchall()]

# Save to JSON
with open('./migration_data/events.json', 'w') as f:
    json.dump(events, f, default=str, indent=2)

print(f'Exported {len(events)} events')

# Export other tables if they exist
for table in ['event_links', 'action_workflows']:
    try:
        cursor.execute(f'SELECT * FROM {table}')
        data = [dict(row) for row in cursor.fetchall()]
        with open(f'./migration_data/{table}.json', 'w') as f:
            json.dump(data, f, default=str, indent=2)
        print(f'Exported {len(data)} {table} records')
    except sqlite3.OperationalError:
        print(f'Table {table} does not exist, skipping')

sqlite_conn.close()
"

# Step 2: Update configuration for PostgreSQL
sed -i 's|sqlite+aiosqlite:///.*|postgresql+asyncpg://chronos:password@localhost:5432/chronos|' chronos.yaml

# Step 3: Initialize PostgreSQL database
createdb chronos
python -m alembic upgrade head

# Step 4: Import data to PostgreSQL
python -c "
import asyncio
import json
import sys
sys.path.append('./src')

from src.core.database import db_service
from src.core.models import ChronosEventDB

async def import_data():
    await db_service.initialize()

    # Import events
    with open('./migration_data/events.json', 'r') as f:
        events = json.load(f)

    for event_data in events:
        # Convert data types
        event_data['created_at'] = datetime.fromisoformat(event_data['created_at'])
        event_data['updated_at'] = datetime.fromisoformat(event_data['updated_at'])
        if event_data['start_time']:
            event_data['start_time'] = datetime.fromisoformat(event_data['start_time'])
        if event_data['end_time']:
            event_data['end_time'] = datetime.fromisoformat(event_data['end_time'])

        # Create and save
        event = ChronosEventDB(**event_data)
        await db_service.save_event(event)

    print(f'Imported {len(events)} events to PostgreSQL')
    await db_service.close()

asyncio.run(import_data())
"

echo "Migration to PostgreSQL completed"
```

#### Large Database Migration

```bash
#!/bin/bash
# migrate_large_database.sh - For databases with millions of records

echo "Large database migration script"

# Step 1: Analyze current database size
python -c "
import sqlite3
import os

db_path = './data/chronos.db'
db_size = os.path.getsize(db_path) / (1024 * 1024)  # MB
print(f'Database size: {db_size:.2f} MB')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Count records
cursor.execute('SELECT COUNT(*) FROM events')
event_count = cursor.fetchone()[0]
print(f'Total events: {event_count:,}')

if event_count > 100000:
    print('Large database detected. Using batch migration.')
    exit(2)  # Special exit code for large database
elif event_count > 10000:
    print('Medium database detected. Using optimized migration.')
    exit(1)
else:
    print('Small database. Using standard migration.')
    exit(0)

conn.close()
"

DB_SIZE_STATUS=$?

if [ $DB_SIZE_STATUS -eq 2 ]; then
    echo "Large database - using batch migration"

    # Batch migration for large databases
    python -c "
import sqlite3
import time
from datetime import datetime

BATCH_SIZE = 1000

# Add sub_tasks column in batches
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# First, add the column
cursor.execute('ALTER TABLE events ADD COLUMN sub_tasks TEXT DEFAULT \"[]\"')

# Update in batches
cursor.execute('SELECT COUNT(*) FROM events')
total = cursor.fetchone()[0]
batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

for i in range(batches):
    offset = i * BATCH_SIZE
    print(f'Processing batch {i+1}/{batches} (offset {offset})')

    # Process batch
    cursor.execute('''
        UPDATE events
        SET sub_tasks = '[]'
        WHERE id IN (
            SELECT id FROM events
            LIMIT ? OFFSET ?
        )
    ''', (BATCH_SIZE, offset))

    conn.commit()
    time.sleep(0.1)  # Small delay to prevent overwhelming the system

print('Batch migration completed')
conn.close()
"

elif [ $DB_SIZE_STATUS -eq 1 ]; then
    echo "Medium database - using optimized migration"
    # Standard Alembic migration with optimizations
    python -m alembic upgrade head

else
    echo "Small database - using standard migration"
    # Standard migration
    python -m alembic upgrade head
fi
```

## Rollback Procedures

### Automated Rollback

```bash
#!/bin/bash
# rollback_from_v22.sh - Automated rollback script

set -e

echo "=== Chronos Engine v2.2 Rollback Script ==="
echo

# Configuration
BACKUP_DIR="$1"  # Backup directory passed as argument
LOG_FILE="./logs/rollback_v22.log"

if [ -z "$BACKUP_DIR" ]; then
    echo "Usage: $0 <backup_directory>"
    echo "Available backups:"
    ls -la ./backups/
    exit 1
fi

if [ ! -d "$BACKUP_DIR" ]; then
    echo "ERROR: Backup directory $BACKUP_DIR not found"
    exit 1
fi

# Create rollback log
mkdir -p logs
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

echo "Rollback started at $(date)"
echo "Using backup: $BACKUP_DIR"
echo

# Step 1: Verify backup contents
echo "Step 1: Verifying backup contents..."
required_files=("chronos.db.backup" "chronos.yaml.backup")
for file in "${required_files[@]}"; do
    if [ ! -f "$BACKUP_DIR/$file" ]; then
        echo "ERROR: Required backup file $file not found"
        exit 1
    fi
    echo "✓ Found $file"
done

# Step 2: Stop Chronos service (if running)
echo "Step 2: Stopping Chronos service..."
if pgrep -f "chronos" > /dev/null; then
    echo "Stopping Chronos processes..."
    pkill -f "chronos" || true
    sleep 5
fi

# Step 3: Create pre-rollback backup
echo "Step 3: Creating pre-rollback backup..."
PRE_ROLLBACK_DIR="./backups/pre_rollback_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$PRE_ROLLBACK_DIR"
cp ./data/chronos.db "$PRE_ROLLBACK_DIR/"
cp chronos.yaml "$PRE_ROLLBACK_DIR/"
echo "Pre-rollback backup saved to $PRE_ROLLBACK_DIR"

# Step 4: Restore database
echo "Step 4: Restoring database..."
cp "$BACKUP_DIR/chronos.db.backup" ./data/chronos.db
echo "Database restored"

# Step 5: Restore configuration
echo "Step 5: Restoring configuration..."
cp "$BACKUP_DIR/chronos.yaml.backup" chronos.yaml
echo "Configuration restored"

# Step 6: Restore custom plugins (if exist)
echo "Step 6: Restoring custom plugins..."
if [ -f "$BACKUP_DIR/custom_plugins.tar.gz" ]; then
    tar -xzf "$BACKUP_DIR/custom_plugins.tar.gz"
    echo "Custom plugins restored"
else
    echo "No custom plugins backup found, skipping"
fi

# Step 7: Verify rollback
echo "Step 7: Verifying rollback..."
python -c "
import sqlite3
import sys

conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# Check that v2.2 tables are gone
v22_tables = ['event_links', 'action_workflows']
for table in v22_tables:
    cursor.execute(f'SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"{table}\"')
    if cursor.fetchone():
        print(f'WARNING: v2.2 table {table} still exists')
    else:
        print(f'✓ v2.2 table {table} removed')

# Check events table structure
cursor.execute('PRAGMA table_info(events)')
columns = [row[1] for row in cursor.fetchall()]
if 'sub_tasks' in columns:
    print('WARNING: sub_tasks column still exists')
else:
    print('✓ sub_tasks column removed')

# Check data integrity
cursor.execute('SELECT COUNT(*) FROM events')
event_count = cursor.fetchone()[0]
print(f'✓ {event_count} events in database')

conn.close()
"

# Step 8: Test basic functionality
echo "Step 8: Testing basic functionality..."
timeout 30 python -c "
import sys
sys.path.append('./src')

from src.core.models import ChronosEvent
from src.core.event_parser import EventParser

# Test basic event creation
event = ChronosEvent(title='Rollback Test Event')
print(f'✓ Event creation: {event.title}')

# Test parser
parser = EventParser()
test_event = {
    'id': 'test',
    'summary': 'Test Event',
    'start': {'dateTime': '2025-01-20T10:00:00Z'},
    'end': {'dateTime': '2025-01-20T11:00:00Z'}
}
parsed = parser.parse_event(test_event)
print(f'✓ Event parsing: {parsed.title}')

print('Basic functionality tests passed')
" || echo "WARNING: Basic functionality tests failed"

echo
echo "=== Rollback Completed ==="
echo "• Database restored from backup"
echo "• Configuration restored"
echo "• v2.2 features removed"
echo "• Pre-rollback backup: $PRE_ROLLBACK_DIR"
echo "• Rollback log: $LOG_FILE"
echo
echo "You can now restart the Chronos service."
```

### Manual Rollback Steps

#### 1. Emergency Rollback (Fast)

```bash
# Emergency rollback - minimal steps
echo "EMERGENCY ROLLBACK - Restoring from backup"

# Stop service
sudo systemctl stop chronos 2>/dev/null || pkill -f chronos

# Restore database (replace with your backup path)
BACKUP_PATH="./backups/pre_v22_20250120_143022"
cp "$BACKUP_PATH/chronos.db.backup" ./data/chronos.db

# Restore configuration
cp "$BACKUP_PATH/chronos.yaml.backup" chronos.yaml

# Start service
sudo systemctl start chronos 2>/dev/null || python -m src.main &

echo "Emergency rollback completed"
```

#### 2. Complete Manual Rollback

```bash
# Step 1: Create current state backup
mkdir -p ./backups/before_rollback_$(date +%Y%m%d_%H%M%S)
cp ./data/chronos.db ./backups/before_rollback_*/
cp chronos.yaml ./backups/before_rollback_*/

# Step 2: Stop all Chronos processes
sudo systemctl stop chronos
pkill -f "python.*chronos"
pkill -f "python.*src.main"

# Step 3: Restore database
BACKUP_DIR="./backups/pre_v22_20250120_143022"  # Your backup directory
cp "$BACKUP_DIR/chronos.db.backup" ./data/chronos.db

# Step 4: Verify database state
python -c "
import sqlite3
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# Check version
try:
    cursor.execute('SELECT version FROM alembic_version')
    version = cursor.fetchone()[0]
    print(f'Database version: {version}')
except:
    print('No alembic version found')

# Check tables
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
tables = [row[0] for row in cursor.fetchall()]
print(f'Tables: {tables}')

conn.close()
"

# Step 5: Restore configuration
cp "$BACKUP_DIR/chronos.yaml.backup" chronos.yaml

# Step 6: Test database connection
python -c "
import asyncio
import sys
sys.path.append('./src')

async def test_db():
    try:
        from src.core.database import db_service
        await db_service.initialize()
        health = await db_service.health_check()
        print(f'Database health: {health}')
        await db_service.close()
        return True
    except Exception as e:
        print(f'Database test failed: {e}')
        return False

success = asyncio.run(test_db())
sys.exit(0 if success else 1)
"

if [ $? -eq 0 ]; then
    echo "Database connection test passed"
else
    echo "Database connection test failed"
    exit 1
fi

# Step 7: Start service
sudo systemctl start chronos

echo "Manual rollback completed"
```

### Partial Rollback (Disable v2.2 Features)

```bash
# Disable v2.2 features without full rollback
echo "Disabling v2.2 features..."

# Update configuration to disable new features
python -c "
import yaml

with open('chronos.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Disable new plugins
if 'plugins' in config:
    config['plugins']['enabled'] = False

# Disable command handler workflows
if 'command_handler' in config:
    config['command_handler']['enabled'] = False

# Disable UNDEFINED guard
if 'undefined_guard' in config:
    config['undefined_guard']['enabled'] = False

# Clear action workflows
config['action_workflows'] = []

# Save updated config
with open('chronos.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False)

print('v2.2 features disabled in configuration')
"

# Restart service with disabled features
sudo systemctl restart chronos

echo "v2.2 features disabled. System running in v2.1 compatibility mode."
```

## Migration Troubleshooting

### Common Issues and Solutions

#### Database Migration Fails

```bash
# Issue: Alembic migration fails
# Solution: Manual migration repair

# Check migration status
python -m alembic current
python -m alembic history

# If migration is stuck, force stamp to head
python -m alembic stamp head

# Then run specific migration
python -m alembic upgrade head

# If still failing, check logs
tail -f ./logs/migration_v22.log
```

#### Configuration Conflicts

```bash
# Issue: Configuration validation fails
# Solution: Reset to default and merge manually

# Backup current config
cp chronos.yaml chronos_problematic.yaml

# Start with clean v2.2 template
cp chronos_v22.yaml chronos.yaml

# Extract specific values from problematic config
python -c "
import yaml

with open('chronos_problematic.yaml', 'r') as f:
    old = yaml.safe_load(f)

print('API Key:', old.get('api', {}).get('api_key', 'not found'))
print('Database URL:', old.get('database', {}).get('url', 'not found'))
# Add other critical settings you need to preserve
"

# Manually edit chronos.yaml with the extracted values
```

#### Plugin Loading Errors

```bash
# Issue: Custom plugins don't load after migration
# Solution: Verify plugin compatibility

# Check plugin syntax
python -m py_compile plugins/custom/*.py

# Test plugin loading
python -c "
import sys
sys.path.append('./plugins/custom')

try:
    from command_handler_plugin import CommandHandlerPlugin
    print('✓ CommandHandlerPlugin loads')
except Exception as e:
    print(f'✗ CommandHandlerPlugin error: {e}')

try:
    from undefined_guard_plugin import UndefinedGuardPlugin
    print('✓ UndefinedGuardPlugin loads')
except Exception as e:
    print(f'✗ UndefinedGuardPlugin error: {e}')
"
```

#### Data Corruption Issues

```bash
# Issue: Database corruption after migration
# Solution: Repair or restore

# Check database integrity
sqlite3 ./data/chronos.db "PRAGMA integrity_check;"

# If corrupted, restore from backup
BACKUP_DIR="./backups/pre_v22_20250120_143022"
cp "$BACKUP_DIR/chronos.db.backup" ./data/chronos.db

# Re-run migration with integrity checks
python -c "
import sqlite3
import json

conn = sqlite3.connect('./data/chronos.db')
conn.execute('PRAGMA integrity_check;')

# Verify critical data
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM events')
count = cursor.fetchone()[0]
print(f'Event count: {count}')

# Check for any NULL values in critical fields
cursor.execute('SELECT COUNT(*) FROM events WHERE title IS NULL OR title = \"\"')
null_titles = cursor.fetchone()[0]
print(f'Events with missing titles: {null_titles}')

conn.close()
"
```

### Migration Validation

#### Post-Migration Checks

```bash
#!/bin/bash
# validate_migration.sh - Comprehensive migration validation

echo "=== Migration Validation ==="

# Check 1: Database schema
echo "1. Database Schema Validation"
python -c "
import sqlite3
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# Required tables
required_tables = ['events', 'event_links', 'action_workflows', 'alembic_version']
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
existing_tables = [row[0] for row in cursor.fetchall()]

for table in required_tables:
    if table in existing_tables:
        print(f'  ✓ {table}')
    else:
        print(f'  ✗ {table} MISSING')

# Required columns in events table
cursor.execute('PRAGMA table_info(events)')
columns = [row[1] for row in cursor.fetchall()]
required_columns = ['id', 'title', 'sub_tasks']
for col in required_columns:
    if col in columns:
        print(f'  ✓ events.{col}')
    else:
        print(f'  ✗ events.{col} MISSING')

conn.close()
"

# Check 2: Configuration validation
echo "2. Configuration Validation"
python validate_config.py chronos.yaml

# Check 3: Feature functionality
echo "3. Feature Functionality"
python integration_test.py

# Check 4: Performance check
echo "4. Performance Check"
python -c "
import time
import sqlite3

start = time.time()
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()

# Test query performance
cursor.execute('SELECT COUNT(*) FROM events')
count = cursor.fetchone()[0]

elapsed = time.time() - start
print(f'  Query time: {elapsed:.3f}s for {count} events')

if elapsed > 1.0:
    print('  ⚠ Performance degradation detected')
else:
    print('  ✓ Performance acceptable')

conn.close()
"

echo "Migration validation completed"
```

---

**Migration Guide Version**: v2.2
**Last Updated**: 2025-01-20
**Support**: Check logs and run validation scripts before seeking support