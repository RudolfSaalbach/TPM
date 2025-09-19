# Chronos Engine v2.1 - Vollständige Feature-Dokumentation

## 📋 Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [Kern-Features](#kern-features)
3. [Sicherheits-Features](#sicherheits-features)
4. [Datenbank & Persistierung](#datenbank--persistierung)
5. [E-Mail & Benachrichtigungen](#e-mail--benachrichtigungen)
6. [Integration & Automatisierung](#integration--automatisierung)
7. [Backup & Recovery](#backup--recovery)
8. [Monitoring & Observability](#monitoring--observability)
9. [Admin Interface](#admin-interface)
10. [API Dokumentation](#api-dokumentation)
11. [Konfiguration](#konfiguration)
12. [Deployment](#deployment)

---

## 🎯 Übersicht

Chronos Engine v2.1 ist ein produktionsreifes, feature-reiches Time Management System mit:

- **Sichere, skalierbare Architektur**
- **Vollständige SQLite-Persistierung**
- **Erweiterte Sicherheitsfeatures**
- **Integrierte E-Mail-Services**
- **Externe System-Integrationen**
- **Umfassendes Monitoring**
- **CRUD-Management ohne Programmierung**

---

## 🚀 Kern-Features

### Event Management

#### Dual-Mode Terminplanung
```yaml
Modi:
  - Frei-Modus: Parallele Termine erlaubt, Konflikt-Warnungen
  - Auto-Plan-Modus: Automatische Konfliktauflösung mit Alternativvorschlägen
```

**Features:**
- **Parallele vs. Auto-Plan Modi** pro Event konfigurierbar
- **Konflikterkennnung** mit visuellen Hinweisen
- **Intelligente Terminvorschläge** basierend auf Verfügbarkeit
- **Automatische Umplanung** bei Konflikten (optional)
- **Free/Busy Integration** für mehrere Teilnehmer

#### Sub-Tasks & Checklisten
```json
{
  "event_id": "evt_123",
  "sub_tasks": [
    {
      "id": "task_1",
      "text": "Agenda vorbereiten",
      "completed": false,
      "created_at": "2025-01-20T10:00:00Z"
    },
    {
      "id": "task_2",
      "text": "Teilnehmer einladen",
      "completed": true,
      "completed_at": "2025-01-20T09:30:00Z"
    }
  ]
}
```

**Features:**
- **To-Do Listen** pro Event
- **Reihenfolgen-Management**
- **Auto-Complete** bei Endzeit + alle Aufgaben erledigt
- **Fortschritts-Tracking**
- **Notizen zu Tasks**

#### Event-Links (n:m Beziehungen)
```sql
CREATE TABLE event_links (
    id INTEGER PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    target_event_id TEXT NOT NULL,
    link_type TEXT DEFAULT 'related',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Link-Typen:**
- `related` - Verwandte Events
- `depends_on` - Abhängigkeiten
- `follows` - Zeitliche Folge
- `replaces` - Event-Ersetzung

---

## 🛡️ Sicherheits-Features

### API-Key Management
```python
# Sichere Key-Generierung
api_key = security_service.generate_api_key(SecurityLevel.HIGH)
# Format: chronos_high_[40-char-token]

# PBKDF2 Hashing mit Salt
key_hash, salt = security_service.hash_api_key(api_key)
# 100.000 Iterationen, SHA256
```

**Features:**
- **Scoped API-Keys** mit granularen Berechtigungen
- **Key-Rotation** mit Ablaufdatum
- **Usage Tracking** mit Nutzungsstatistiken
- **Security-Level** basierte Key-Stärke
- **Rate Limiting** pro Key und IP

#### API-Scopes
```python
class APIScope(Enum):
    EVENTS_READ = "events.read"
    EVENTS_WRITE = "events.write"
    COMMANDS_MANAGE = "commands.manage"
    ADMIN = "admin"
    TEMPLATES_READ = "templates.read"
    TEMPLATES_WRITE = "templates.write"
    WHITELISTS_MANAGE = "whitelists.manage"
    WORKFLOWS_MANAGE = "workflows.manage"
    BACKUPS_MANAGE = "backups.manage"
    INTEGRATIONS_MANAGE = "integrations.manage"
```

### HMAC-Signaturen
```python
# Webhook-Sicherheit
signature = security_service.generate_signature(payload, timestamp)
# Format: sha256=[hash]

# Replay-Schutz
is_valid = security_service.verify_signature(
    payload, signature, timestamp, max_age=300
)
```

### Rate Limiting
```python
# Multi-Level Rate Limiting
identifier_limit = 1000  # Pro API-Key
ip_limit = 5000         # Pro IP-Adresse

# Automatic Lockout
max_failed_attempts = 5
lockout_duration = 30   # Minuten
```

### Audit-Logging
```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    actor TEXT NOT NULL,
    actor_type TEXT DEFAULT 'api_key',
    scope TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_values TEXT,
    new_values TEXT,
    ip_address TEXT,
    user_agent TEXT,
    security_level TEXT,
    risk_score INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT 1
);
```

**Features:**
- **Unveränderliches Log** aller Änderungen
- **Risk Assessment** mit Score 0-100
- **Security Incident Detection**
- **IP-basierte Anomalie-Erkennung**
- **Context-aware Logging**

---

## 💾 Datenbank & Persistierung

### SQLite Optimierungen
```sql
-- WAL-Modus für bessere Concurrency
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=30000;
PRAGMA cache_size=-64000;  -- 64MB Cache
```

### Enhanced Database Service
```python
class DatabaseService:
    async def get_session(self, retry_count: int = 3):
        # Retry-Logic mit exponential backoff
        # Connection Health Checks
        # Automatic Error Recovery
        # Transaction Management
```

**Features:**
- **WAL-Modus** für bessere Performance
- **Connection Pooling** mit Health Checks
- **Retry-Logic** bei Verbindungsfehlern
- **Transaction Safety** mit Rollback
- **Database Metrics** und Monitoring

### Schema-Erweiterungen
```sql
-- Neue Tabellen für erweiterte Features
CREATE TABLE whitelists (
    id INTEGER PRIMARY KEY,
    system_name TEXT NOT NULL,
    action_name TEXT NOT NULL,
    allowed_params JSON,
    enabled BOOLEAN DEFAULT 1
);

CREATE TABLE workflows (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    trigger_action TEXT NOT NULL,
    follow_action TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1
);

CREATE TABLE email_templates (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    subject_template TEXT NOT NULL,
    html_body_template TEXT,
    text_body_template TEXT,
    variables JSON
);
```

---

## 📧 E-Mail & Benachrichtigungen

### E-Mail Service
```python
# HTML/Text E-Mails mit Templates
await email_service.send_template_email(
    template_id=1,
    to=["user@example.com"],
    variables={
        "event": {"title": "Team Meeting", "start_time": "2025-01-20 14:00"},
        "user": {"name": "John Doe"}
    }
)
```

**Features:**
- **HTML + Text** Dual-Format Support
- **Template Engine** mit Platzhaltern
- **Anhänge** (Attachments)
- **SMTP-Integration** mit TLS/SSL
- **Delivery Tracking** mit Message-IDs
- **Template-Kategorien** für Organisation

### Template-System
```html
<!-- E-Mail Template Beispiel -->
<h2>{{event.title}}</h2>
<p>Liebe/r {{user.name}},</p>
<p>{{message}}</p>

{{#if event.location}}
<p><strong>Ort:</strong> {{event.location}}</p>
{{/if}}

<div style="background: #f8f9fa; padding: 15px;">
    <h3>Event Details:</h3>
    <p><strong>Start:</strong> {{event.start_time}}</p>
    <p><strong>Dauer:</strong> {{event.duration}}</p>
</div>
```

### Benachrichtigungs-Integration
```python
# Automatische Benachrichtigungen
notification_triggers = [
    "event_created",
    "event_updated",
    "event_reminder",
    "action_completed",
    "security_incident"
]
```

---

## 🔗 Integration & Automatisierung

### Outbox Pattern
```python
# Zuverlässige Message Delivery
await outbox_service.add_entry(
    target_system="TELEGRAM",
    event_type="notification",
    payload={"message": "Event created", "chat_id": 123},
    idempotency_key="unique_key_123"
)
```

**Features:**
- **Guaranteed Delivery** mit Retry-Logic
- **Idempotenz** verhindert Duplikate
- **Dead Letter Queue** für failed Messages
- **Exponential Backoff** bei Fehlern
- **Status Tracking** aller Nachrichten

### Telegram Integration
```python
# Bot-Commands
commands = [
    "/start",    # Willkommensnachricht
    "/events",   # Events auflisten
    "/create",   # Event erstellen
    "/status",   # System-Status
    "/help"      # Hilfe anzeigen
]

# Natural Language Processing
patterns = [
    "NOTIZ: [text]",           # Notiz speichern
    "ACTION: SYSTEM command",   # Action ausführen
    "URL: [url] [description]", # URL speichern
    "Meeting tomorrow 2pm"      # Event erstellen
]
```

### n8n Automation
```json
{
  "workflow_templates": [
    {
      "name": "Action Request",
      "payload": {
        "type": "action_request",
        "action_id": "{{action_id}}",
        "command": "{{command}}",
        "target_system": "{{target_system}}",
        "parameters": "{{parameters}}",
        "event": "{{event}}"
      }
    },
    {
      "name": "Event Notification",
      "payload": {
        "type": "event_notification",
        "event": "{{event}}",
        "notification_type": "{{type}}",
        "recipients": "{{recipients}}"
      }
    }
  ]
}
```

### Workflow-Engine
```python
# If-This-Then-That Workflows
class Workflow:
    trigger_action: str      # "SEND_EMAIL"
    trigger_system: str      # "SMTP"
    trigger_status: str      # "COMPLETED"
    follow_action: str       # "NOTIFY_TELEGRAM"
    follow_system: str       # "TELEGRAM"
    follow_params: dict      # {"message": "Email sent"}
```

### Whitelists & Security
```python
# Erlaubte Systeme und Actions
whitelists = [
    {
        "system": "TELEGRAM",
        "action": "SEND_MESSAGE",
        "allowed_params": {
            "message": "string",
            "chat_id": "int",
            "priority": "string"
        }
    },
    {
        "system": "N8N",
        "action": "TRIGGER_WORKFLOW",
        "allowed_params": {
            "workflow_id": "string",
            "data": "object"
        }
    }
]
```

---

## 💾 Backup & Recovery

### Automated Backup System
```python
# Backup-Konfiguration
backup_config = BackupConfig(
    name="daily_backup",
    include_database=True,
    include_config=True,
    include_templates=True,
    include_logs=False,
    compression_level=6
)

# Backup erstellen
result = await backup_service.create_backup(backup_config)
```

**Features:**
- **Ein-Klick Backups** über Admin UI
- **Geplante Backups** (täglich/wöchentlich)
- **ZIP-Archive** mit Komprimierung
- **SHA256 Checksums** für Integrität
- **Restore-Anweisungen** in jeder Backup-Datei
- **Retention Policies** (7 täglich, 4 wöchentlich)

### Backup-Inhalte
```
chronos_backup_20250120_143022.zip
├── data/
│   ├── chronos.db              # SQLite Datenbank
│   └── chronos.db-wal          # WAL-Datei
├── config/
│   └── chronos.yaml            # Konfiguration
├── templates/                  # HTML-Templates
├── static/                     # Assets
├── backup_metadata.json        # Backup-Info
└── RESTORE_INSTRUCTIONS.txt    # Wiederherstellungsanleitung
```

### Backup-Scheduler
```python
# Automatische Backups
backup_jobs = [
    {
        "name": "daily_full",
        "schedule": "0 2 * * *",        # Täglich 2:00 Uhr
        "type": "full",
        "retention_days": 7
    },
    {
        "name": "weekly_archive",
        "schedule": "0 1 * * 0",        # Sonntags 1:00 Uhr
        "type": "full",
        "retention_days": 30
    }
]
```

---

## 📊 Monitoring & Observability

### Health Checks
```python
health_checks = [
    {
        "name": "database",
        "interval": 60,              # Sekunden
        "timeout": 10,
        "critical": True,
        "description": "Database connectivity"
    },
    {
        "name": "disk_space",
        "interval": 300,
        "critical": True,
        "thresholds": {
            "warning": 20,           # % frei
            "critical": 5
        }
    },
    {
        "name": "memory",
        "interval": 60,
        "thresholds": {
            "warning": 80,           # % belegt
            "critical": 95
        }
    }
]
```

### System Monitoring
```python
# Gesammelte Metriken
system_metrics = [
    "cpu_percent",
    "memory_percent",
    "memory_used_bytes",
    "disk_percent",
    "network_bytes_sent",
    "network_bytes_recv",
    "process_memory_rss",
    "process_cpu_percent",
    "process_num_threads"
]
```

### Performance Tracking
```python
# Performance Timer
async with PerformanceTimer(logger, "database_query", table="events"):
    result = await session.execute(query)

# Metrics Collection
metrics_collector.record_timer("api_request_duration", 150.5, {
    "method": "POST",
    "endpoint": "/api/v1/events",
    "status": "200"
})
```

### Structured Logging
```json
{
  "timestamp": "2025-01-20T14:30:22.123Z",
  "level": "INFO",
  "category": "api",
  "message": "POST /api/v1/events - 201",
  "component": "chronos_api",
  "duration_ms": 45.2,
  "session_id": "sess_abc123",
  "user_id": "user_456",
  "ip_address": "192.168.1.100",
  "metadata": {
    "method": "POST",
    "path": "/api/v1/events",
    "status_code": 201,
    "event_id": "evt_789"
  }
}
```

---

## 🔧 Admin Interface

### CRUD Management ohne Programmierung

#### 1. System Whitelists
```html
<!-- Admin UI für Whitelists -->
<form method="post" action="/admin/whitelists/new">
    <input name="system_name" placeholder="TELEGRAM">
    <input name="action_name" placeholder="SEND_MESSAGE">
    <textarea name="allowed_params">
    {
      "message": "string",
      "priority": "int",
      "channels": "list"
    }
    </textarea>
    <input type="checkbox" name="enabled" checked>
</form>
```

#### 2. Workflow Management
```html
<!-- If-This-Then-That Workflows -->
<form method="post" action="/admin/workflows/new">
    <input name="name" placeholder="Email to Telegram">
    <select name="trigger_action">
        <option value="SEND_EMAIL">SEND_EMAIL</option>
        <option value="CREATE_EVENT">CREATE_EVENT</option>
    </select>
    <select name="trigger_status">
        <option value="COMPLETED">COMPLETED</option>
        <option value="FAILED">FAILED</option>
    </select>
    <input name="follow_action" placeholder="NOTIFY_TELEGRAM">
    <textarea name="follow_params">
    {
      "message": "Email wurde versendet an {{recipient}}",
      "chat_id": 123456789
    }
    </textarea>
</form>
```

#### 3. E-Mail Templates
```html
<!-- Template Editor mit Vorschau -->
<form method="post" action="/admin/email-templates/new">
    <input name="name" placeholder="Event Reminder">
    <input name="subject_template" placeholder="Erinnerung: {{event.title}}">

    <!-- HTML Editor -->
    <textarea name="html_body_template" rows="10">
    <h2>{{event.title}}</h2>
    <p>Hallo {{user.name}},</p>
    <p>{{message}}</p>

    {{#if event.location}}
    <p><strong>Ort:</strong> {{event.location}}</p>
    {{/if}}
    </textarea>

    <!-- Text Version -->
    <textarea name="text_body_template" rows="5">
    {{event.title}}

    Hallo {{user.name}},
    {{message}}

    {{#if event.location}}Ort: {{event.location}}{{/if}}
    </textarea>

    <input name="variables" placeholder="event,user,message">
    <select name="category">
        <option value="notification">Benachrichtigung</option>
        <option value="reminder">Erinnerung</option>
        <option value="report">Bericht</option>
    </select>
</form>
```

### Admin Dashboard
```html
<!-- Übersichts-Dashboard -->
<div class="admin-dashboard">
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number">142</div>
            <div class="stat-label">Total Events</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">8</div>
            <div class="stat-label">Email Templates</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">3</div>
            <div class="stat-label">Active Workflows</div>
        </div>
    </div>

    <div class="quick-actions">
        <a href="/admin/whitelists">Manage Whitelists</a>
        <a href="/admin/workflows">Manage Workflows</a>
        <a href="/admin/email-templates">Manage Templates</a>
        <a href="/admin/backups">Backup Management</a>
        <a href="/admin/system">System Information</a>
    </div>
</div>
```

---

## 🌐 API Dokumentation

### Event API
```http
# Event erstellen
POST /api/v1/events
Content-Type: application/json
Authorization: Bearer chronos_[api_key]

{
  "title": "Team Meeting",
  "description": "Weekly sync meeting",
  "start_time": "2025-01-20T14:00:00Z",
  "end_time": "2025-01-20T15:00:00Z",
  "event_type": "meeting",
  "location": "Conference Room A",
  "attendees": ["john@example.com", "jane@example.com"],
  "tags": ["team", "weekly"],
  "mode": "auto_plan",
  "sub_tasks": [
    {"text": "Prepare agenda", "completed": false},
    {"text": "Send invitations", "completed": true}
  ]
}
```

### Template API
```http
# Template anwenden
POST /api/v1/templates/{template_id}/apply
Content-Type: application/json
Authorization: Bearer chronos_[api_key]

{
  "variables": {
    "event": {
      "title": "Project Review",
      "date": "2025-01-21",
      "location": "Room B"
    },
    "user": {
      "name": "Alice Smith",
      "email": "alice@example.com"
    }
  },
  "recipients": ["alice@example.com", "bob@example.com"]
}
```

### Admin API
```http
# Whitelist erstellen
POST /api/v1/admin/whitelists
Content-Type: application/json
Authorization: Bearer chronos_[admin_api_key]

{
  "system_name": "TELEGRAM",
  "action_name": "SEND_MESSAGE",
  "allowed_params": {
    "message": "string",
    "chat_id": "int",
    "priority": "string"
  },
  "enabled": true
}
```

### Health Check API
```http
# System Health
GET /health
Accept: application/json

# Response
{
  "status": "healthy",
  "timestamp": "2025-01-20T14:30:22.123Z",
  "version": "2.1.0",
  "database": {
    "status": "connected",
    "response_time_ms": 12.5
  },
  "checks": [
    {
      "name": "database",
      "status": "healthy",
      "message": "Database connection OK",
      "duration_ms": 8.2
    }
  ],
  "metrics": {
    "cpu_percent": 15.2,
    "memory_percent": 42.1,
    "disk_percent": 68.3
  }
}
```

---

## ⚙️ Konfiguration

### Basis-Konfiguration (chronos.yaml)
```yaml
# Chronos Engine Configuration
environment: production

# Database Configuration
database:
  url: sqlite+aiosqlite:///./data/chronos.db
  max_connections: 20
  pool_timeout: 30
  echo_sql: false
  backup_enabled: true
  backup_schedule: "0 2 * * *"

# API Configuration
api:
  host: 0.0.0.0
  port: 8080
  debug: false
  workers: 1
  cors_origins: ["https://your-domain.com"]
  max_request_size: 16777216  # 16MB
  timeout: 30

# Security Configuration
security:
  api_key_expiry_days: 365
  session_timeout_minutes: 480
  max_failed_attempts: 5
  lockout_duration_minutes: 30
  rate_limit_per_hour: 1000
  require_https: true
  allowed_origins: ["https://your-domain.com"]
  encryption_enabled: true

# SMTP Configuration
smtp:
  host: smtp.your-domain.com
  port: 587
  username: chronos@your-domain.com
  password: "${SMTP_PASSWORD}"
  use_tls: true
  from_email: chronos@your-domain.com
  from_name: Chronos Engine

# Logging Configuration
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file_enabled: true
  file_path: logs/chronos.log
  file_max_size: 10485760  # 10MB
  file_backup_count: 5
  console_enabled: true

# Integration Configuration
integrations:
  telegram_enabled: true
  telegram_bot_token: "${TELEGRAM_BOT_TOKEN}"
  telegram_webhook_secret: "${TELEGRAM_WEBHOOK_SECRET}"
  telegram_allowed_chats: [123456789, 987654321]

  n8n_enabled: true
  n8n_webhook_base_url: "https://n8n.your-domain.com/webhook"
  n8n_webhook_secret: "${N8N_WEBHOOK_SECRET}"
```

### Environment Variables
```bash
# Production Environment
CHRONOS_ENVIRONMENT=production

# Database
CHRONOS_DB_URL=sqlite+aiosqlite:///./data/chronos.db
CHRONOS_DB_MAX_CONNECTIONS=20

# API
CHRONOS_API_HOST=0.0.0.0
CHRONOS_API_PORT=8080
CHRONOS_API_DEBUG=false

# Security
CHRONOS_SECURITY_REQUIRE_HTTPS=true
CHRONOS_SECURITY_SECRET_KEY=your-secret-key-here

# SMTP
CHRONOS_SMTP_HOST=smtp.your-domain.com
CHRONOS_SMTP_PORT=587
CHRONOS_SMTP_USERNAME=chronos@your-domain.com
CHRONOS_SMTP_PASSWORD=your-smtp-password
CHRONOS_SMTP_FROM_EMAIL=chronos@your-domain.com

# Logging
CHRONOS_LOG_LEVEL=INFO

# Integrations
CHRONOS_TELEGRAM_BOT_TOKEN=your-bot-token
CHRONOS_N8N_WEBHOOK_URL=https://n8n.your-domain.com/webhook
```

---

## 🚀 Deployment

### Docker Deployment
```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ src/
COPY templates/ templates/
COPY static/ static/
COPY chronos.yaml .

# Create data directory
RUN mkdir -p data logs backups

# Set permissions
RUN chmod 750 data logs backups

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Run application
CMD ["python", "-m", "src.main"]
```

### Docker Compose
```yaml
# docker-compose.yml
version: '3.8'

services:
  chronos:
    build: .
    ports:
      - "8080:8080"
    environment:
      - CHRONOS_ENVIRONMENT=production
      - CHRONOS_SECURITY_REQUIRE_HTTPS=true
      - CHRONOS_SMTP_HOST=${SMTP_HOST}
      - CHRONOS_SMTP_USERNAME=${SMTP_USERNAME}
      - CHRONOS_SMTP_PASSWORD=${SMTP_PASSWORD}
      - CHRONOS_TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./backups:/app/backups
      - ./config/chronos.yaml:/app/chronos.yaml:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - chronos
    restart: unless-stopped
```

### Systemd Service
```ini
# /etc/systemd/system/chronos.service
[Unit]
Description=Chronos Engine v2.1
After=network.target

[Service]
Type=simple
User=chronos
Group=chronos
WorkingDirectory=/opt/chronos
Environment=CHRONOS_ENVIRONMENT=production
ExecStart=/opt/chronos/venv/bin/python -m src.main
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=always
RestartSec=10

# Security
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/chronos/data /opt/chronos/logs /opt/chronos/backups

[Install]
WantedBy=multi-user.target
```

### Production Checklist
```bash
# 1. System Setup
sudo useradd -r -s /bin/false chronos
sudo mkdir -p /opt/chronos/{data,logs,backups}
sudo chown -R chronos:chronos /opt/chronos
sudo chmod 750 /opt/chronos/{data,logs,backups}

# 2. SSL/TLS Setup
sudo mkdir -p /opt/chronos/ssl
sudo chmod 700 /opt/chronos/ssl
# Copy SSL certificates

# 3. Environment Setup
sudo -u chronos python -m venv /opt/chronos/venv
sudo -u chronos /opt/chronos/venv/bin/pip install -r requirements.txt

# 4. Configuration
sudo cp chronos.yaml /opt/chronos/
sudo chown chronos:chronos /opt/chronos/chronos.yaml
sudo chmod 600 /opt/chronos/chronos.yaml

# 5. Service Installation
sudo cp chronos.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable chronos
sudo systemctl start chronos

# 6. Monitoring Setup
sudo systemctl status chronos
sudo journalctl -u chronos -f

# 7. Health Check
curl -f http://localhost:8080/health
```

---

## 📈 Performance & Skalierung

### Performance Features
- **Async/Await** durchgehend für Non-blocking Operations
- **Connection Pooling** für Database und externe APIs
- **Resource Management** mit automatischem Cleanup
- **Memory Monitoring** mit Garbage Collection
- **WAL-Modus** für bessere SQLite Performance

### Monitoring Metriken
```python
performance_metrics = [
    "api_request_duration",
    "database_query_time",
    "email_send_duration",
    "backup_creation_time",
    "memory_usage_mb",
    "cpu_utilization_percent",
    "active_connections_count",
    "outbox_queue_size"
]
```

### Skalierungs-Empfehlungen
- **Load Balancer** für horizontale Skalierung
- **Redis** für Session Storage (optional)
- **PostgreSQL** für größere Installationen
- **Kubernetes** für Container-Orchestrierung
- **Prometheus/Grafana** für Monitoring

---

## 🔧 Wartung & Updates

### Routine-Wartung
```bash
# 1. Log-Rotation (automatisch)
sudo logrotate /etc/logrotate.d/chronos

# 2. Backup-Bereinigung
curl -X POST http://localhost:8080/admin/backups/cleanup

# 3. Database-Optimierung
sqlite3 data/chronos.db "VACUUM;"
sqlite3 data/chronos.db "ANALYZE;"

# 4. Metriken-Check
curl http://localhost:8080/api/v1/admin/metrics

# 5. Security-Audit
curl http://localhost:8080/api/v1/admin/security/incidents
```

### Update-Prozess
```bash
# 1. Backup erstellen
curl -X POST http://localhost:8080/admin/backups/create

# 2. Service stoppen
sudo systemctl stop chronos

# 3. Code aktualisieren
cd /opt/chronos
sudo -u chronos git pull
sudo -u chronos /opt/chronos/venv/bin/pip install -r requirements.txt

# 4. Database-Migration (falls nötig)
sudo -u chronos /opt/chronos/venv/bin/python -m alembic upgrade head

# 5. Service starten
sudo systemctl start chronos

# 6. Health Check
curl -f http://localhost:8080/health
```

---

## 🎯 Feature-Zusammenfassung

### ✅ Vollständig Implementiert

| Kategorie | Features | Status |
|-----------|----------|---------|
| **Event Management** | Dual-Mode Planung, Sub-Tasks, Event-Links | ✅ Fertig |
| **Sicherheit** | API-Keys, HMAC, Rate Limiting, Audit-Log | ✅ Fertig |
| **Datenbank** | SQLite WAL, Connection Pooling, Health Checks | ✅ Fertig |
| **E-Mail** | HTML/Text Templates, SMTP, Tracking | ✅ Fertig |
| **Integration** | Telegram Bot, n8n Webhooks, Outbox Pattern | ✅ Fertig |
| **Backup** | Automated Backups, Scheduling, Restore | ✅ Fertig |
| **Monitoring** | Health Checks, Metrics, Performance Tracking | ✅ Fertig |
| **Admin UI** | CRUD Management, Templates, Workflows | ✅ Fertig |
| **Konfiguration** | Environment-based, Validation, Security | ✅ Fertig |
| **Resource Management** | Memory Management, Task Cleanup | ✅ Fertig |

### 🚀 Produktions-Features

| Feature | Beschreibung | Implementiert |
|---------|--------------|---------------|
| **Error Handling** | Comprehensive Error Recovery | ✅ |
| **Logging** | Structured JSON Logging | ✅ |
| **Security** | Enterprise-grade Security | ✅ |
| **Performance** | Optimized für Production | ✅ |
| **Monitoring** | Complete Observability | ✅ |
| **Backup** | Automated Disaster Recovery | ✅ |
| **Documentation** | Complete Documentation | ✅ |

---

**Chronos Engine v2.1 ist vollständig produktionsbereit mit allen Enterprise-Features implementiert.** 🎉