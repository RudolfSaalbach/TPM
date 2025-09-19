# Chronos Engine v2.2 - Complete Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying Chronos Engine v2.2 in production environments. The deployment includes database migrations, configuration updates, security hardening, and monitoring setup.

## Prerequisites

### System Requirements
- **Python**: 3.9+ (tested with 3.11, 3.12, 3.13)
- **Database**: SQLite 3.35+ (for JSON support) or PostgreSQL 12+
- **Memory**: Minimum 512MB RAM (2GB+ recommended for production)
- **Storage**: 1GB+ free space (depends on event volume)
- **Network**: HTTPS capability for API endpoints

### Dependencies
- SQLAlchemy 2.0+
- FastAPI 0.100+
- Alembic for migrations
- Pydantic for validation
- asyncio support

## Pre-Deployment Checklist

### 1. Backup Existing Installation
```bash
# Backup database
cp ./data/chronos.db ./backups/chronos_pre_v22_$(date +%Y%m%d_%H%M%S).db

# Backup configuration
cp chronos.yaml ./backups/chronos_config_backup.yaml

# Backup custom plugins (if any)
tar -czf ./backups/custom_plugins_backup.tar.gz plugins/custom/
```

### 2. Environment Verification
```bash
# Check Python version
python --version  # Should be 3.9+

# Check SQLite version (if using SQLite)
python -c "import sqlite3; print(sqlite3.sqlite_version)"  # Should be 3.35+

# Test database connectivity
python -c "from src.core.database import db_service; import asyncio; asyncio.run(db_service.health_check())"
```

### 3. Security Review
- [ ] API keys rotated and secured
- [ ] Action whitelists reviewed and minimized
- [ ] HTTPS certificates updated
- [ ] Firewall rules configured
- [ ] Access logs enabled

## Deployment Steps

### Step 1: Code Deployment

#### Option A: Git Deployment
```bash
# Pull latest v2.2 code
git fetch origin
git checkout v2.2.0  # or specific release tag
git pull origin v2.2.0

# Verify code integrity
python -c "from src.core.models import SubTask; print('v2.2 models available')"
```

#### Option B: Package Deployment
```bash
# If using packaged deployment
tar -xzf chronos-v2.2.0.tar.gz
cd chronos-v2.2.0/
```

### Step 2: Configuration Update

#### Update Configuration File
```bash
# Copy v2.2 configuration template
cp chronos_v22.yaml chronos.yaml

# Edit configuration for your environment
vim chronos.yaml
```

#### Required Configuration Changes
```yaml
# chronos.yaml - Production Configuration
version: "2.2"
debug: false
timezone: "UTC"

# Database - Update for your environment
database:
  url: "sqlite+aiosqlite:///./data/chronos.db"  # or PostgreSQL URL
  echo_sql: false
  pool_size: 10

# API Security
api:
  host: "0.0.0.0"
  port: 8000
  api_key: "your-secure-production-api-key"  # CHANGE THIS
  cors_origins: ["https://your-frontend-domain.com"]
  rate_limit: "100/minute"

# Command Handler Security
command_handler:
  enabled: true
  action_whitelist:
    - "DEPLOY"
    - "STATUS_CHECK"
    - "BACKUP"
    # Add only commands you actually need

# UNDEFINED Guard
undefined_guard:
  enabled: true
  extra_patterns: []  # Add custom patterns if needed

# Workflows (configure based on your automation needs)
action_workflows:
  - trigger_command: "DEPLOY"
    trigger_system: "production"
    follow_up_command: "STATUS_CHECK"
    follow_up_system: "monitoring"
    delay_seconds: 30
```

### Step 3: Database Migration

#### Pre-Migration Verification
```bash
# Check current database revision
python -m alembic current

# Check pending migrations
python -m alembic heads
```

#### Execute Migration
```bash
# Run the v2.2 migration
python -m alembic upgrade head

# Verify migration success
python -c "
from src.core.database import db_service
import asyncio
print('Schema info:', asyncio.run(db_service.get_schema_info()))
"
```

#### Migration Verification
```bash
# Test new tables exist
python -c "
import sqlite3
conn = sqlite3.connect('./data/chronos.db')
cursor = conn.cursor()
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
tables = [row[0] for row in cursor.fetchall()]
print('Tables:', tables)
assert 'event_links' in tables
assert 'action_workflows' in tables
print('Migration verified!')
conn.close()
"
```

### Step 4: Plugin Configuration

#### Verify Plugin Loading
```bash
# Test plugin loading
python -c "
import asyncio
from src.core.plugin_manager import PluginManager

async def test_plugins():
    pm = PluginManager({'config': {}})
    success = await pm.initialize()
    print(f'Plugin manager initialized: {success}')
    plugins = pm.list_plugins()
    for plugin in plugins:
        print(f'  - {plugin[\"name\"]} v{plugin[\"version\"]} ({plugin[\"type\"]})')
    await pm.cleanup()

asyncio.run(test_plugins())
"
```

#### Configure Plugin Priority
```yaml
# In chronos.yaml
plugins:
  enabled: true
  custom_dir: "plugins/custom"
  auto_load: true
  load_order:
    - "command_handler"    # Must be first
    - "undefined_guard"    # Should be early
    - "meeting_optimizer"  # Other plugins after
```

### Step 5: Security Hardening

#### API Security
```yaml
# chronos.yaml - Security Configuration
security:
  api_key_rotation_days: 90
  command_timeout_seconds: 300
  max_workflow_depth: 5
  audit_log: true
  encrypt_sensitive_data: true

# Rate limiting
api:
  rate_limit: "100/minute"
  cors_origins: ["https://yourdomain.com"]  # Specific origins only
```

#### File Permissions
```bash
# Secure configuration file
chmod 600 chronos.yaml

# Secure database
chmod 600 ./data/chronos.db

# Secure plugin directory
chmod -R 755 plugins/
chmod 644 plugins/custom/*.py
```

#### Network Security
```bash
# Configure firewall (example for ufw)
sudo ufw allow 8000/tcp  # Or your configured port
sudo ufw enable

# If using reverse proxy
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### Step 6: Service Configuration

#### Systemd Service (Linux)
```bash
# Create service file
sudo tee /etc/systemd/system/chronos.service > /dev/null <<EOF
[Unit]
Description=Chronos Engine v2.2
After=network.target

[Service]
Type=simple
User=chronos
Group=chronos
WorkingDirectory=/opt/chronos
Environment=PYTHONPATH=/opt/chronos
ExecStart=/opt/chronos/venv/bin/python -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable chronos
sudo systemctl start chronos
```

#### Docker Deployment
```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . .

# Create data directory
RUN mkdir -p data

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "-m", "src.main"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  chronos:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./chronos.yaml:/app/chronos.yaml
    environment:
      - PYTHONPATH=/app
    restart: unless-stopped
```

### Step 7: Monitoring Setup

#### Health Check Endpoint
```bash
# Test health endpoint
curl -H "Authorization: Bearer your-api-key" \
     http://localhost:8000/api/v1/health
```

#### Log Configuration
```yaml
# chronos.yaml - Logging
logging:
  level: "INFO"  # Use "DEBUG" only for troubleshooting
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "./logs/chronos.log"
  rotation: "daily"
  retention: 30
```

#### Monitoring Integration
```bash
# Create log directory
mkdir -p logs

# Set up log rotation
sudo tee /etc/logrotate.d/chronos > /dev/null <<EOF
/opt/chronos/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    copytruncate
}
EOF
```

### Step 8: Testing and Validation

#### Functional Testing
```bash
# Run integration tests
python integration_test.py

# Run feature validation
python v22_feature_validation.py

# Run backwards compatibility test
python backwards_compatibility_test.py

# Run security/performance test
python security_performance_test.py
```

#### API Testing
```bash
# Test v2.1 API (backwards compatibility)
curl -X POST \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Event",
    "start_time": "2025-01-20T10:00:00Z",
    "end_time": "2025-01-20T11:00:00Z"
  }' \
  http://localhost:8000/api/v1/events

# Test v2.2 API (new features)
curl -X POST \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "source_event_id": "event-1",
    "target_event_id": "event-2",
    "link_type": "depends_on"
  }' \
  http://localhost:8000/api/v2.2/event-links
```

#### Feature Testing
```bash
# Test sub-task parsing
python -c "
from src.core.event_parser import EventParser
parser = EventParser()
desc = '''
Tasks:
[ ] Review changes
[x] Update docs
[ ] Deploy
'''
tasks = parser._parse_sub_tasks(desc)
print(f'Parsed {len(tasks)} tasks')
for task in tasks:
    print(f'  - {task.text}: {task.completed}')
"

# Test command processing
python -c "
import asyncio
from plugins.custom.command_handler_plugin import CommandHandlerPlugin
from src.core.models import ChronosEvent

async def test_cmd():
    plugin = CommandHandlerPlugin()
    await plugin.initialize({
        'config': {
            'command_handler': {
                'action_whitelist': ['DEPLOY'],
                'enabled': True
            }
        }
    })

    event = ChronosEvent(title='ACTION: DEPLOY production')
    result = await plugin.process_event(event)
    print(f'Command processed: {result is None}')

    await plugin.cleanup()

asyncio.run(test_cmd())
"
```

## Post-Deployment

### Performance Monitoring
```bash
# Monitor resource usage
top -p $(pgrep -f chronos)

# Monitor database size
ls -lah ./data/chronos.db

# Monitor log growth
du -sh logs/
```

### Backup Schedule
```bash
# Add to crontab
crontab -e

# Add these lines:
# Daily database backup
0 2 * * * cp /opt/chronos/data/chronos.db /backups/chronos_$(date +\%Y\%m\%d).db

# Weekly full backup
0 3 * * 0 tar -czf /backups/chronos_full_$(date +\%Y\%m\%d).tar.gz /opt/chronos/

# Cleanup old backups (keep 30 days)
0 4 * * * find /backups -name "chronos_*.db" -mtime +30 -delete
```

### Security Monitoring
```bash
# Monitor failed authentications
grep "401" logs/chronos.log

# Monitor command executions
grep "CMD_HANDLER" logs/chronos.log

# Monitor UNDEFINED detections
grep "UNDEFINED_GUARD" logs/chronos.log
```

## Troubleshooting

### Common Issues

#### Migration Fails
```bash
# Check current revision
python -m alembic current

# Check for conflicts
python -m alembic heads

# Manual fix (if needed)
python -m alembic stamp head
```

#### Plugins Not Loading
```bash
# Check plugin directory
ls -la plugins/custom/

# Check syntax
python -m py_compile plugins/custom/command_handler_plugin.py

# Check imports
python -c "from plugins.custom.command_handler_plugin import CommandHandlerPlugin; print('OK')"
```

#### Performance Issues
```bash
# Check database size
sqlite3 ./data/chronos.db "VACUUM;"

# Check memory usage
ps aux | grep chronos

# Check for long-running operations
grep "slow" logs/chronos.log
```

#### API Not Responding
```bash
# Check if service is running
systemctl status chronos

# Check port binding
netstat -tlnp | grep 8000

# Check logs
tail -f logs/chronos.log
```

## Rollback Procedure

### Emergency Rollback
```bash
# 1. Stop service
sudo systemctl stop chronos

# 2. Restore database
cp ./backups/chronos_pre_v22_*.db ./data/chronos.db

# 3. Restore configuration
cp ./backups/chronos_config_backup.yaml chronos.yaml

# 4. Checkout previous version
git checkout v2.1.x

# 5. Start service
sudo systemctl start chronos
```

### Gradual Rollback
```bash
# 1. Disable v2.2 features in config
vim chronos.yaml
# Set all v2.2 features to false

# 2. Restart service
sudo systemctl restart chronos

# 3. Monitor for issues
tail -f logs/chronos.log
```

## Support and Maintenance

### Regular Maintenance Tasks
- **Weekly**: Review logs for errors or warnings
- **Monthly**: Update API keys, check backups
- **Quarterly**: Review and update action whitelists
- **Annually**: Security audit and dependency updates

### Getting Help
- Check logs: `tail -f logs/chronos.log`
- Run diagnostics: `python integration_test.py`
- Community support: GitHub Issues
- Professional support: Contact development team

## Appendix

### Configuration File Reference
See `chronos_v22.yaml` for complete configuration options.

### API Documentation
See `API_DOCUMENTATION.md` for complete API reference.

### Security Best Practices
- Rotate API keys regularly
- Use HTTPS in production
- Limit action whitelist to minimum required
- Monitor audit logs
- Keep backups current

---

**Deployment Checklist Summary:**
- [ ] System requirements verified
- [ ] Backup completed
- [ ] Code deployed
- [ ] Configuration updated
- [ ] Database migrated
- [ ] Plugins configured
- [ ] Security hardened
- [ ] Service configured
- [ ] Monitoring enabled
- [ ] Testing completed
- [ ] Documentation updated