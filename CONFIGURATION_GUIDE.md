# Chronos Engine v2.2 - Configuration Guide

## Overview

This guide provides comprehensive information on configuring Chronos Engine v2.2 for different environments and use cases. All configuration is managed through the `chronos.yaml` file.

## Configuration File Structure

### Basic Structure

```yaml
# chronos.yaml - Complete Configuration Template
version: "2.2"
debug: false
timezone: "UTC"

# Database Configuration
database:
  url: "sqlite+aiosqlite:///./data/chronos.db"
  echo_sql: false
  pool_size: 10
  pool_timeout: 30
  max_overflow: 20

# API Configuration
api:
  host: "0.0.0.0"
  port: 8000
  api_key: "your-secure-api-key"
  cors_origins: ["*"]
  rate_limit: "100/minute"
  docs_url: "/docs"
  redoc_url: "/redoc"

# Logging Configuration
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "./logs/chronos.log"
  rotation: "daily"
  retention: 30

# Plugin Configuration
plugins:
  enabled: true
  custom_dir: "plugins/custom"
  auto_load: true
  load_order:
    - "command_handler"
    - "undefined_guard"

# Command Handler Plugin
command_handler:
  enabled: true
  action_whitelist:
    - "DEPLOY"
    - "STATUS_CHECK"
    - "BACKUP"
    - "RESTART"
  command_timeout: 300
  max_concurrent: 5

# UNDEFINED Guard Plugin
undefined_guard:
  enabled: true
  extra_patterns: []
  exclude_calendars: ["google_calendar", "outlook"]

# Action Workflows
action_workflows:
  - trigger_command: "DEPLOY"
    trigger_system: "production"
    follow_up_command: "STATUS_CHECK"
    follow_up_system: "monitoring"
    delay_seconds: 30
    follow_up_params:
      timeout: 300
      retries: 3

# Security Settings
security:
  api_key_rotation_days: 90
  command_timeout_seconds: 300
  max_workflow_depth: 5
  audit_log: true
  encrypt_sensitive_data: true
```

## Environment-Specific Configurations

### Development Environment

```yaml
# chronos_dev.yaml
version: "2.2"
debug: true
timezone: "UTC"

database:
  url: "sqlite+aiosqlite:///./data/chronos_dev.db"
  echo_sql: true  # Enable SQL logging for debugging
  pool_size: 5

api:
  host: "127.0.0.1"
  port: 8000
  api_key: "dev-api-key-12345"
  cors_origins: ["http://localhost:3000", "http://127.0.0.1:3000"]
  rate_limit: "1000/minute"  # Relaxed for development

logging:
  level: "DEBUG"
  file: "./logs/chronos_dev.log"

command_handler:
  enabled: true
  action_whitelist:
    - "DEPLOY"
    - "STATUS_CHECK"
    - "BACKUP"
    - "TEST_CMD"  # Additional test commands for dev

undefined_guard:
  enabled: true
  extra_patterns:
    - "test:"  # Catch test patterns in dev

# Minimal workflows for testing
action_workflows:
  - trigger_command: "TEST_CMD"
    trigger_system: "dev"
    follow_up_command: "STATUS_CHECK"
    follow_up_system: "dev"
    delay_seconds: 5
```

### Production Environment

```yaml
# chronos_prod.yaml
version: "2.2"
debug: false
timezone: "UTC"

database:
  url: "postgresql+asyncpg://chronos:password@localhost:5432/chronos_prod"
  echo_sql: false
  pool_size: 20
  pool_timeout: 60
  max_overflow: 30

api:
  host: "0.0.0.0"
  port: 8000
  api_key: "prod-secure-key-a1b2c3d4e5f6"
  cors_origins: ["https://chronos.company.com"]
  rate_limit: "100/minute"
  docs_url: null  # Disable docs in production
  redoc_url: null

logging:
  level: "INFO"
  file: "/var/log/chronos/chronos.log"
  rotation: "daily"
  retention: 90

command_handler:
  enabled: true
  action_whitelist:
    - "DEPLOY"
    - "STATUS_CHECK"
    - "BACKUP"
    - "RESTART"
  command_timeout: 600  # 10 minutes for production commands
  max_concurrent: 3

undefined_guard:
  enabled: true
  exclude_calendars: ["google_calendar", "outlook_calendar"]

# Production workflows
action_workflows:
  - trigger_command: "DEPLOY"
    trigger_system: "production"
    follow_up_command: "STATUS_CHECK"
    follow_up_system: "monitoring"
    delay_seconds: 60
    follow_up_params:
      timeout: 600
      retries: 5
      notification_channels: ["email", "slack"]

  - trigger_command: "BACKUP"
    trigger_system: "database"
    follow_up_command: "VERIFY_BACKUP"
    follow_up_system: "backup_service"
    delay_seconds: 300
    follow_up_params:
      checksum_verify: true
      notification_on_failure: true

security:
  api_key_rotation_days: 30  # More frequent rotation in prod
  command_timeout_seconds: 600
  max_workflow_depth: 3
  audit_log: true
  encrypt_sensitive_data: true
```

### Testing Environment

```yaml
# chronos_test.yaml
version: "2.2"
debug: false
timezone: "UTC"

database:
  url: "sqlite+aiosqlite:///:memory:"  # In-memory for tests
  echo_sql: false
  pool_size: 1

api:
  host: "127.0.0.1"
  port: 8001  # Different port to avoid conflicts
  api_key: "test-api-key"
  cors_origins: ["*"]
  rate_limit: "10000/minute"  # No rate limiting in tests

logging:
  level: "WARNING"  # Reduce noise in test output
  file: "./logs/chronos_test.log"

plugins:
  enabled: true
  auto_load: false  # Manual plugin loading in tests

command_handler:
  enabled: true
  action_whitelist:
    - "TEST_DEPLOY"
    - "TEST_STATUS"
    - "MOCK_CMD"
  command_timeout: 30

undefined_guard:
  enabled: true

# Test workflows
action_workflows:
  - trigger_command: "TEST_DEPLOY"
    trigger_system: "test"
    follow_up_command: "TEST_STATUS"
    follow_up_system: "test"
    delay_seconds: 1

security:
  api_key_rotation_days: 999  # Disable rotation in tests
  command_timeout_seconds: 30
  max_workflow_depth: 2
  audit_log: false
  encrypt_sensitive_data: false
```

## Feature-Specific Configuration

### Database Configuration

#### SQLite (Default)
```yaml
database:
  url: "sqlite+aiosqlite:///./data/chronos.db"
  echo_sql: false
  pool_size: 10
  # SQLite-specific settings
  journal_mode: "WAL"  # Write-Ahead Logging for better concurrency
  synchronous: "NORMAL"  # Balance between safety and speed
```

#### PostgreSQL
```yaml
database:
  url: "postgresql+asyncpg://username:password@host:port/database"
  echo_sql: false
  pool_size: 20
  pool_timeout: 60
  max_overflow: 30
  # PostgreSQL-specific settings
  ssl_mode: "require"
  application_name: "chronos_v22"
```

#### MySQL/MariaDB
```yaml
database:
  url: "mysql+aiomysql://username:password@host:port/database"
  echo_sql: false
  pool_size: 15
  pool_timeout: 45
  max_overflow: 25
  # MySQL-specific settings
  charset: "utf8mb4"
  autocommit: false
```

### Command Handler Configuration

#### Basic Setup
```yaml
command_handler:
  enabled: true
  action_whitelist:
    - "DEPLOY"
    - "STATUS_CHECK"
    - "BACKUP"
  command_timeout: 300
  max_concurrent: 5
```

#### Advanced Setup
```yaml
command_handler:
  enabled: true
  action_whitelist:
    - "DEPLOY"
    - "STATUS_CHECK"
    - "BACKUP"
    - "RESTART"
    - "UPDATE_CONFIG"
    - "SCALE_SERVICE"
  command_timeout: 600
  max_concurrent: 10

  # System-specific configurations
  system_configs:
    production:
      timeout: 900
      retries: 3
      notification_webhook: "https://hooks.slack.com/..."

    staging:
      timeout: 300
      retries: 1
      notification_webhook: null

  # Command-specific configurations
  command_configs:
    DEPLOY:
      timeout: 1200  # 20 minutes for deployments
      required_params: ["environment", "version"]

    BACKUP:
      timeout: 3600  # 1 hour for backups
      required_params: ["database_name"]
```

### UNDEFINED Guard Configuration

#### Basic Setup
```yaml
undefined_guard:
  enabled: true
  extra_patterns: []
  exclude_calendars: ["google_calendar"]
```

#### Advanced Setup
```yaml
undefined_guard:
  enabled: true

  # Additional patterns to detect as malformed
  extra_patterns:
    - "note:"      # Common typo for NOTIZ:
    - "cmd:"       # Common abbreviation
    - "link:"      # Common typo for URL:
    - "task:"      # Common alternative
    - "todo:"      # Common alternative

  # Calendars to exclude from processing
  exclude_calendars:
    - "google_calendar"
    - "outlook_calendar"
    - "apple_calendar"

  # Events to exclude from processing
  exclude_patterns:
    - "^\\[SYSTEM\\]"    # System events
    - "^\\[AUTO\\]"      # Auto-generated events
    - "^Meeting with"    # Standard meeting titles

  # Case sensitivity settings
  case_sensitive: true

  # Skip events that are already in progress
  skip_in_progress: true
```

### Workflow Configuration

#### Simple Workflows
```yaml
action_workflows:
  # Deploy → Status Check
  - trigger_command: "DEPLOY"
    trigger_system: "production"
    follow_up_command: "STATUS_CHECK"
    follow_up_system: "monitoring"
    delay_seconds: 30

  # Backup → Verify
  - trigger_command: "BACKUP"
    trigger_system: "database"
    follow_up_command: "VERIFY_BACKUP"
    follow_up_system: "backup_service"
    delay_seconds: 300
```

#### Complex Workflows
```yaml
action_workflows:
  # Full deployment pipeline
  - trigger_command: "DEPLOY"
    trigger_system: "production"
    follow_up_command: "STATUS_CHECK"
    follow_up_system: "monitoring"
    delay_seconds: 60
    follow_up_params:
      timeout: 600
      retries: 5
      endpoints_to_check:
        - "/health"
        - "/metrics"
        - "/ready"
      notification_channels:
        - "email"
        - "slack"
      escalation_timeout: 1800

  # Database maintenance workflow
  - trigger_command: "BACKUP"
    trigger_system: "primary_db"
    follow_up_command: "ANALYZE_TABLES"
    follow_up_system: "primary_db"
    delay_seconds: 600
    follow_up_params:
      tables_to_analyze: ["events", "event_links", "action_workflows"]
      vacuum_after_analyze: true
      notification_email: "dba@company.com"

  # Scaling workflow
  - trigger_command: "SCALE_SERVICE"
    trigger_system: "web_cluster"
    follow_up_command: "MONITOR_SCALING"
    follow_up_system: "orchestrator"
    delay_seconds: 120
    follow_up_params:
      monitor_duration: 1800
      success_criteria:
        - "cpu_usage < 70%"
        - "memory_usage < 80%"
        - "response_time < 200ms"
```

### Security Configuration

#### Basic Security
```yaml
security:
  api_key_rotation_days: 90
  command_timeout_seconds: 300
  max_workflow_depth: 5
  audit_log: true
```

#### Advanced Security
```yaml
security:
  # API key management
  api_key_rotation_days: 30
  api_key_length: 32
  api_key_algorithm: "HS256"

  # Command security
  command_timeout_seconds: 600
  max_concurrent_commands: 10
  command_rate_limit: "10/minute"

  # Workflow security
  max_workflow_depth: 3
  workflow_timeout_seconds: 3600
  max_workflow_params_size: 1024

  # Audit and logging
  audit_log: true
  audit_log_file: "./logs/chronos_audit.log"
  audit_retention_days: 365

  # Data protection
  encrypt_sensitive_data: true
  encryption_key_rotation_days: 30

  # Network security
  allowed_ip_ranges:
    - "10.0.0.0/8"
    - "192.168.0.0/16"

  # Rate limiting
  global_rate_limit: "1000/hour"
  per_key_rate_limit: "100/minute"
  burst_allowance: 10
```

### Logging Configuration

#### Development Logging
```yaml
logging:
  level: "DEBUG"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
  file: "./logs/chronos_dev.log"
  console: true
  rotation: "size"
  max_size: "10MB"
  backup_count: 3
```

#### Production Logging
```yaml
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "/var/log/chronos/chronos.log"
  console: false
  rotation: "daily"
  retention: 90

  # Structured logging for production
  structured: true
  json_format: true

  # Log different components to different files
  loggers:
    command_handler:
      file: "/var/log/chronos/commands.log"
      level: "INFO"

    undefined_guard:
      file: "/var/log/chronos/undefined.log"
      level: "WARNING"

    api:
      file: "/var/log/chronos/api.log"
      level: "INFO"
```

## Configuration Validation

### Validation Script

Create `validate_config.py`:

```python
#!/usr/bin/env python3
import yaml
import sys
from jsonschema import validate, ValidationError

# Configuration schema
CONFIG_SCHEMA = {
    "type": "object",
    "required": ["version", "database", "api"],
    "properties": {
        "version": {"type": "string", "enum": ["2.2"]},
        "debug": {"type": "boolean"},
        "timezone": {"type": "string"},
        "database": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "echo_sql": {"type": "boolean"},
                "pool_size": {"type": "integer", "minimum": 1, "maximum": 100}
            }
        },
        "api": {
            "type": "object",
            "required": ["host", "port", "api_key"],
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "api_key": {"type": "string", "minLength": 8},
                "rate_limit": {"type": "string"}
            }
        },
        "command_handler": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "action_whitelist": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
    }
}

def validate_config(config_file):
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        validate(config, CONFIG_SCHEMA)
        print(f"✓ Configuration in {config_file} is valid")
        return True

    except FileNotFoundError:
        print(f"✗ Configuration file {config_file} not found")
        return False
    except yaml.YAMLError as e:
        print(f"✗ YAML syntax error in {config_file}: {e}")
        return False
    except ValidationError as e:
        print(f"✗ Configuration validation error: {e.message}")
        return False

if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "chronos.yaml"
    success = validate_config(config_file)
    sys.exit(0 if success else 1)
```

Usage:
```bash
python validate_config.py chronos.yaml
python validate_config.py chronos_prod.yaml
```

## Environment Variables

You can override configuration values using environment variables:

```bash
# Database
export CHRONOS_DB_URL="postgresql://user:pass@host:5432/db"
export CHRONOS_DB_POOL_SIZE=20

# API
export CHRONOS_API_HOST="0.0.0.0"
export CHRONOS_API_PORT=8000
export CHRONOS_API_KEY="secure-production-key"

# Logging
export CHRONOS_LOG_LEVEL="INFO"
export CHRONOS_LOG_FILE="/var/log/chronos/chronos.log"

# Features
export CHRONOS_COMMAND_HANDLER_ENABLED=true
export CHRONOS_UNDEFINED_GUARD_ENABLED=true
```

Environment variables take precedence over configuration file values.

## Configuration Management

### Docker Configuration

```dockerfile
# Dockerfile with configuration
FROM python:3.11-slim

# Copy application
WORKDIR /app
COPY . .

# Install dependencies
RUN pip install -r requirements.txt

# Create configuration from template
RUN cp chronos_docker.yaml chronos.yaml

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
      - "${CHRONOS_PORT:-8000}:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./chronos_prod.yaml:/app/chronos.yaml:ro
    environment:
      - CHRONOS_API_KEY=${CHRONOS_API_KEY}
      - CHRONOS_DB_URL=${CHRONOS_DB_URL}
    restart: unless-stopped
```

### Kubernetes Configuration

```yaml
# chronos-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: chronos-config
data:
  chronos.yaml: |
    version: "2.2"
    debug: false
    timezone: "UTC"

    database:
      url: "postgresql://chronos:password@postgres:5432/chronos"
      pool_size: 20

    api:
      host: "0.0.0.0"
      port: 8000
      api_key: "{{ .Values.apiKey }}"
      cors_origins: ["https://chronos.company.com"]

    logging:
      level: "INFO"
      file: "/app/logs/chronos.log"

    command_handler:
      enabled: true
      action_whitelist: ["DEPLOY", "STATUS_CHECK", "BACKUP"]

    undefined_guard:
      enabled: true

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chronos
spec:
  replicas: 3
  selector:
    matchLabels:
      app: chronos
  template:
    metadata:
      labels:
        app: chronos
    spec:
      containers:
      - name: chronos
        image: chronos:v2.2
        ports:
        - containerPort: 8000
        volumeMounts:
        - name: config
          mountPath: /app/chronos.yaml
          subPath: chronos.yaml
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: config
        configMap:
          name: chronos-config
      - name: logs
        emptyDir: {}
```

## Configuration Best Practices

### Security Best Practices

1. **API Key Management**
   - Use strong, randomly generated API keys (32+ characters)
   - Rotate API keys regularly (monthly in production)
   - Never commit API keys to version control
   - Use environment variables or secret management systems

2. **Command Whitelisting**
   - Keep action whitelist minimal (only required commands)
   - Review whitelist quarterly
   - Use specific command names, avoid wildcards
   - Document purpose of each whitelisted command

3. **Database Security**
   - Use encrypted connections (SSL/TLS)
   - Restrict database access by IP
   - Use dedicated database users with minimal privileges
   - Regular database backups with encryption

### Performance Best Practices

1. **Database Configuration**
   - Tune pool size based on expected load
   - Use connection pooling for high-traffic scenarios
   - Consider read replicas for heavy read workloads
   - Monitor database performance metrics

2. **Logging Configuration**
   - Use appropriate log levels (INFO in production)
   - Implement log rotation to prevent disk issues
   - Consider centralized logging for distributed deployments
   - Monitor log file sizes and retention

3. **Rate Limiting**
   - Set realistic rate limits based on usage patterns
   - Implement burst allowances for spike handling
   - Monitor rate limit violations
   - Adjust limits based on performance testing

### Maintenance Best Practices

1. **Configuration Management**
   - Version control all configuration files
   - Use environment-specific configurations
   - Validate configurations before deployment
   - Document all configuration changes

2. **Monitoring**
   - Monitor application health endpoints
   - Set up alerts for configuration errors
   - Track configuration drift
   - Regular configuration audits

3. **Backup and Recovery**
   - Backup configuration files with database
   - Test configuration restore procedures
   - Document rollback procedures
   - Keep configuration change history

---

**Configuration Version**: v2.2
**Last Updated**: 2025-01-20
**Validation**: Use `validate_config.py` to verify configurations