# Chronos Engine v2.2 - Feature Overview

## Core Architecture

Chronos Engine v2.2 is built around a **CalDAV-first architecture** with comprehensive calendar management capabilities, unified backend abstraction, and advanced event processing.

## 🆕 v2.2 Enhancements
- **Unified Configuration Management**: Single `config/chronos.yaml` file eliminates configuration confusion
- **UTF-8 Encoding Support**: Proper handling of special characters in configuration files
- **Enhanced Calendar Detection**: Improved CalDAV calendar recognition and error handling
- **Demo & Testing Framework**: Complete test event generation scripts for all calendar types
- **Production Data Integration**: Elimination of all mock/fake data throughout the application
- **Improved Error Handling**: Better diagnostics for configuration and connection issues

### 🎯 Key Features

#### 1. **CalDAV/Radicale Integration (Primary Backend)**
- **Native CalDAV Support**: Full RFC 4791 and RFC 6578 compliance
- **Sync-Collection Support**: Efficient incremental sync with sync-tokens
- **Multiple Calendar Support**: Process multiple CalDAV collections simultaneously
- **Authentication Modes**: Support for none, basic, and digest authentication
- **ETag Conflict Resolution**: Safe concurrent event modifications
- **X-CHRONOS-* Properties**: Custom idempotency markers for event tracking

#### 2. **Unified Backend Architecture**
- **SourceAdapter Interface**: Unified API for all calendar backends
- **Seamless Backend Switching**: Switch between CalDAV and Google Calendar via API
- **Backend-Agnostic Processing**: Calendar repair and event processing work with any backend
- **Runtime Configuration**: Change backends without service restart

#### 3. **Advanced Event Processing**
- **Calendar Repairer**: Intelligent event parsing and standardization
  - Birthday detection and formatting (`BDAY: John Doe 15.01.1990` → `🎉 Birthday: John Doe (15.01)`)
  - Anniversary handling (`ANNIV: Wedding 10.06.2010` → `🎖️ Anniversary: Wedding since 10.06 (15 years)`)
  - Automatic recurrence rules for yearly events
- **Idempotency System**: Prevents duplicate processing across backends
- **Event Normalization**: Consistent event format regardless of source

#### 4. **Comprehensive API**
- **CalDAV Management Endpoints**: Full CalDAV server control
  - Backend information and connection testing
  - Calendar listing and individual sync control
  - Event CRUD operations with ETag support
  - Backend switching without restart
- **Legacy API Compatibility**: All existing v1 endpoints continue to work
- **Interactive Documentation**: OpenAPI 3.0 with Swagger UI at `/docs`

#### 5. **Multi-Calendar Support**
- **Calendar-Specific Configuration**: Individual settings per calendar
- **Read-Only Calendars**: Protect critical calendars from modifications
- **Timezone Support**: Per-calendar timezone configuration
- **Parallel Processing**: Concurrent calendar synchronization

#### 6. **Event Data Portability**
- **JSON Export/Import**: Complete event data with metadata preservation
- **Transactional Processing**: Atomic import operations with rollback
- **Schema Validation**: Comprehensive data validation on import
- **API Authentication**: Secure export/import via API keys

## Technical Capabilities

### Database & Storage
- **SQLite Primary**: Fast, file-based storage with WAL mode
- **PostgreSQL Support**: Production-ready with connection pooling
- **UTC Timestamps**: Consistent timezone handling
- **Full-Text Search**: Fast event content searching
- **Schema Migrations**: Automated database updates

### Security & Authentication
- **API Key Protection**: Bearer token authentication for all endpoints
- **Rate Limiting**: Configurable request throttling
- **Input Validation**: Comprehensive request data validation
- **Audit Logging**: Complete operation tracking
- **Secure Headers**: CORS and security header configuration

### Performance & Reliability
- **Async Processing**: Non-blocking FastAPI with async SQLAlchemy
- **Connection Pooling**: Efficient database connection management
- **Caching**: Smart caching for repeated operations
- **Health Monitoring**: Comprehensive health check endpoints
- **Error Handling**: Graceful error recovery and reporting

### Operations & Monitoring
- **Health Endpoints**: `/health` with database and service status
- **Metrics Integration**: Performance and usage metrics
- **Structured Logging**: JSON logging for production environments
- **Docker Support**: Container-ready with docker-compose
- **Configuration Management**: YAML-based configuration with validation

## Calendar Backend Comparison

| Feature | CalDAV/Radicale | Google Calendar |
|---------|-----------------|-----------------|
| **Self-Hosted** | ✅ Yes | ❌ No |
| **Privacy Control** | ✅ Full | ⚠️ Limited |
| **Sync Efficiency** | ✅ RFC 6578 sync-collection | ✅ Sync tokens |
| **Event Modifications** | ✅ ETag-based | ✅ ETag-based |
| **Multiple Calendars** | ✅ Yes | ✅ Yes |
| **Authentication** | ✅ Basic/Digest/None | 🔑 OAuth 2.0 |
| **Offline Access** | ✅ Local network | ❌ Internet required |
| **Custom Properties** | ✅ X-CHRONOS-* | ✅ extendedProperties |

## Configuration Examples

### Basic CalDAV Setup
```yaml
calendar_source:
  type: "caldav"
caldav:
  calendars:
    - id: "personal"
      url: "http://localhost:5232/user/personal/"
      read_only: false
```

### Production CalDAV with Authentication
```yaml
calendar_source:
  type: "caldav"
caldav:
  auth:
    mode: "basic"
    username: "chronos-user"
    password_ref: "env:CALDAV_PASSWORD"
  transport:
    verify_tls: true
```

### Hybrid Setup (CalDAV + Google)
```yaml
calendar_source:
  type: "caldav"  # Primary backend
caldav:
  calendars: [...]
google:
  enabled: true  # Available for switching
  credentials_file: "config/credentials.json"
```

## API Examples

### Backend Management
```bash
# Get current backend information
GET /caldav/backend/info

# Test CalDAV connection
POST /caldav/connection/test

# Switch to Google Calendar
POST /caldav/backend/switch
{
  "backend_type": "google",
  "config": {"google": {"enabled": true}}
}
```

### Calendar Operations
```bash
# List all calendars
GET /caldav/calendars

# Sync specific calendar
POST /caldav/calendars/automation/sync?days_ahead=30

# Create event
POST /caldav/calendars/automation/events
{
  "summary": "Team Meeting",
  "start_time": "2025-01-20T14:00:00",
  "end_time": "2025-01-20T15:00:00"
}
```

### Event Data Portability
```bash
# Export events
GET /api/v1/events/export?start_date=2025-01-01&end_date=2025-12-31

# Import events
POST /api/v1/events/import
{
  "events": [...],
  "import_mode": "merge"
}
```

## Use Cases

### Personal Calendar Management
- Self-hosted calendar with privacy control
- Automatic birthday and anniversary formatting
- Multiple calendar organization (work, personal, family)
- Cross-device synchronization via CalDAV

### Team Collaboration
- Shared CalDAV server for team calendars
- Read-only calendars for company events
- API-driven event creation from external systems
- Backend switching for migration scenarios

### Enterprise Integration
- Production-ready with PostgreSQL backend
- API key authentication and rate limiting
- Audit logging and monitoring
- Docker deployment with configuration management

### Development & Testing
- Local CalDAV server for development
- Mock backends for testing
- API documentation and testing tools
- Configuration validation and examples

## Roadmap

### Current (v2.1)
- ✅ CalDAV/Radicale integration complete
- ✅ Unified backend architecture
- ✅ Event data portability
- ✅ Comprehensive testing and documentation

### Future Considerations
- 🔄 Additional CalDAV server support (Nextcloud, DAVx⁵)
- 🔄 Webhook notifications for event changes
- 🔄 Advanced calendar sharing and permissions
- 🔄 Calendar federation and synchronization

---

**Version**: v2.1
**Architecture**: CalDAV-first with Google Calendar fallback
**Documentation**: See `docs/` for detailed guides
**Configuration**: See `config/examples/` for setup examples