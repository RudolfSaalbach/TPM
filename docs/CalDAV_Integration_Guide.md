# CalDAV/Radicale Integration Guide

## Overview

Chronos Engine v2.1 now features comprehensive CalDAV/Radicale support as the primary calendar backend, replacing Google Calendar as the default. This guide covers setup, configuration, and usage of the new CalDAV integration.

## Features

### ✅ What's New
- **CalDAV as Default Backend** - Radicale/CalDAV is now the primary calendar source
- **Unified SourceAdapter Interface** - Seamless switching between CalDAV and Google Calendar
- **RFC 6578 Sync Support** - Efficient incremental sync with sync-tokens
- **X-CHRONOS-* Idempotency Markers** - Backend-agnostic event repair tracking
- **Multi-Calendar Support** - Process multiple CalDAV collections simultaneously
- **Backend-Agnostic Pipeline** - Calendar repair works with both CalDAV and Google
- **REST API Integration** - Full CalDAV management via API endpoints
- **ETag-based Conflict Resolution** - Safe concurrent event modifications

### 🎯 Key Benefits
- **Self-Hosted Control** - No dependency on external services
- **Better Privacy** - Keep your calendar data on your own infrastructure
- **Faster Sync** - Direct network access to your Radicale server
- **Unified Processing** - Same repair rules work for all backends
- **Easy Migration** - Seamless switch between CalDAV and Google Calendar

## Quick Start

### 1. Basic CalDAV Configuration

Create or update your `config/chronos.yaml`:

```yaml
# Chronos Engine v2.1 - CalDAV Configuration
version: 1

# CalDAV is now the default backend
calendar_source:
  type: "caldav"
  timezone_default: "Europe/Berlin"

# CalDAV/Radicale Configuration
caldav:
  calendars:
    - id: "automation"
      alias: "Automation"
      url: "http://10.210.1.1:5232/radicaleuser/automation/"
      read_only: false
      timezone: "Europe/Berlin"
    - id: "dates"
      alias: "Dates"
      url: "http://10.210.1.1:5232/radicaleuser/dates/"
      read_only: false
      timezone: "Europe/Berlin"
    - id: "special"
      alias: "Special"
      url: "http://10.210.1.1:5232/radicaleuser/special/"
      read_only: true
      timezone: "Europe/Berlin"

  auth:
    mode: "none"              # "none" | "basic" | "digest"
    username: "radicaleuser"  # only used if mode ≠ "none"
    password_ref: "env:RADICALE_PASSWORD"

  transport:
    verify_tls: false         # false for http/WireGuard, true for https
    connect_timeout_s: 5
    read_timeout_s: 15

  sync:
    use_sync_collection: true # RFC 6578 sync-token preferred
    window_days: 400          # Fallback time window
    parallel_requests: 3

  write:
    if_match: true            # ETag protection
    retry_conflict: 1
    include_vtimezone: true
```

### 2. Start the Service

```bash
# Start with CalDAV backend
python -m src.main

# Check health status
curl -H "Authorization: Bearer your-api-key" http://localhost:8080/health
```

### 3. Verify CalDAV Connection

```bash
# Test CalDAV connection
curl -X POST -H "Authorization: Bearer your-api-key" \
  http://localhost:8080/caldav/connection/test

# List available calendars
curl -H "Authorization: Bearer your-api-key" \
  http://localhost:8080/caldav/calendars

# Get backend information
curl -H "Authorization: Bearer your-api-key" \
  http://localhost:8080/caldav/backend/info
```

## Configuration Details

### Calendar Source Configuration

```yaml
calendar_source:
  type: "caldav"                    # Primary backend type
  timezone_default: "Europe/Berlin" # Default timezone for events
```

**Supported backend types:**
- `caldav` - Radicale/CalDAV server (default)
- `google` - Google Calendar (fallback)

### CalDAV Server Configuration

```yaml
caldav:
  calendars:
    - id: "unique-calendar-id"      # Internal identifier
      alias: "Human Readable Name"  # Display name
      url: "http://server:port/path/" # CalDAV collection URL
      read_only: false              # Allow write operations
      timezone: "Europe/Berlin"     # Calendar timezone
```

**Multiple calendar support:**
- Each calendar is processed independently
- Events are tagged with their calendar source
- Read-only calendars are skipped for write operations

### Authentication Configuration

```yaml
caldav:
  auth:
    mode: "basic"                   # Authentication method
    username: "your-username"       # CalDAV username
    password_ref: "env:PASSWORD"    # Password reference
```

**Authentication modes:**
- `none` - No authentication (local/trusted network)
- `basic` - HTTP Basic Authentication
- `digest` - HTTP Digest Authentication

**Password references:**
- `env:VARIABLE_NAME` - Read from environment variable
- `file:/path/to/file` - Read from file
- `plain:password` - Plain text (not recommended)

### Transport Configuration

```yaml
caldav:
  transport:
    verify_tls: false              # TLS certificate verification
    connect_timeout_s: 5           # Connection timeout
    read_timeout_s: 15             # Read timeout
```

**TLS Configuration:**
- `verify_tls: false` - For HTTP or self-signed certificates
- `verify_tls: true` - For HTTPS with valid certificates

### Sync Configuration

```yaml
caldav:
  sync:
    use_sync_collection: true      # Use RFC 6578 sync-collection
    window_days: 400               # Time window for calendar-query fallback
    parallel_requests: 3           # Concurrent requests per calendar
```

**Sync strategies:**
1. **Sync-Collection (RFC 6578)** - Preferred, uses sync-tokens for incremental updates
2. **Calendar-Query (RFC 4791)** - Fallback, uses time-range filters

### Write Configuration

```yaml
caldav:
  write:
    if_match: true                 # Use ETag for conflict detection
    retry_conflict: 1              # Retry attempts on conflict
    include_vtimezone: true        # Include VTIMEZONE in events
```

## Idempotency Markers

CalDAV events use X-CHRONOS-* properties for tracking repair operations:

```yaml
repair_and_enrich:
  idempotency:
    marker_keys:
      cleaned: "X-CHRONOS-CLEANED"
      rule_id: "X-CHRONOS-RULE-ID"
      signature: "X-CHRONOS-SIGNATURE"
      original_summary: "X-CHRONOS-ORIGINAL-SUMMARY"
      payload: "X-CHRONOS-PAYLOAD"
```

**Example CalDAV event with markers:**
```ics
BEGIN:VEVENT
UID:birthday-event-123
SUMMARY:🎉 Birthday: John Doe (15.01)
DTSTART;VALUE=DATE:20250115
DTEND;VALUE=DATE:20250116
RRULE:FREQ=YEARLY
X-CHRONOS-CLEANED:true
X-CHRONOS-RULE-ID:bday
X-CHRONOS-SIGNATURE:abc123def456
X-CHRONOS-ORIGINAL-SUMMARY:BDAY: John Doe 15.01.1990
X-CHRONOS-PAYLOAD:{"name": "John Doe", "date": "1990-01-15"}
END:VEVENT
```

## API Endpoints

### Backend Management

```bash
# Get backend information
GET /caldav/backend/info

# Test connection
POST /caldav/connection/test

# Switch backend
POST /caldav/backend/switch
{
  "backend_type": "google",
  "config": { ... }
}
```

### Calendar Management

```bash
# List calendars
GET /caldav/calendars

# Sync specific calendar
POST /caldav/calendars/{calendar_id}/sync?days_ahead=30&force_refresh=false
```

### Event Operations

```bash
# Create event
POST /caldav/calendars/{calendar_id}/events
{
  "summary": "New Event",
  "start_time": "2025-01-15T14:00:00",
  "end_time": "2025-01-15T15:00:00",
  "all_day": false
}

# Get event
GET /caldav/calendars/{calendar_id}/events/{event_id}

# Update event
PATCH /caldav/calendars/{calendar_id}/events/{event_id}
{
  "summary": "Updated Event Title"
}

# Delete event
DELETE /caldav/calendars/{calendar_id}/events/{event_id}
```

## Migration Guide

### From Google Calendar to CalDAV

1. **Export Google Calendar data** (if needed):
   ```bash
   # Use existing export functionality
   GET /events/{event_id}/export
   ```

2. **Update configuration** to use CalDAV:
   ```yaml
   calendar_source:
     type: "caldav"  # Changed from "google"
   ```

3. **Import events** (if needed):
   ```bash
   POST /events/import
   ```

4. **Switch backend via API**:
   ```bash
   POST /caldav/backend/switch
   {
     "backend_type": "caldav",
     "config": { "caldav": { ... } }
   }
   ```

### Hybrid Setup (CalDAV + Google)

Keep both backends available for testing:

```yaml
calendar_source:
  type: "caldav"  # Primary backend

# CalDAV configuration
caldav:
  calendars: [ ... ]

# Google Calendar as fallback
google:
  enabled: false  # Disabled by default
  credentials_file: "config/credentials.json"
  token_file: "config/token.json"
```

Switch backends dynamically:
```bash
# Switch to Google Calendar
POST /caldav/backend/switch
{
  "backend_type": "google",
  "config": {
    "google": {
      "enabled": true,
      "credentials_file": "config/credentials.json"
    }
  }
}
```

## Troubleshooting

### Connection Issues

**Problem:** CalDAV connection fails
```
Failed to validate connection after switching to caldav
```

**Solutions:**
1. Check network connectivity:
   ```bash
   curl -v http://10.210.1.1:5232/radicaleuser/automation/
   ```

2. Verify authentication:
   ```bash
   curl -u username:password http://server:5232/path/
   ```

3. Check calendar URLs:
   ```bash
   # List collections
   curl -X PROPFIND http://server:5232/user/
   ```

### Sync Issues

**Problem:** Events not syncing
```
Error syncing CalDAV calendar automation: HTTP 404
```

**Solutions:**
1. Verify calendar URLs in configuration
2. Check calendar permissions
3. Test with calendar-query instead of sync-collection:
   ```yaml
   caldav:
     sync:
       use_sync_collection: false
   ```

### Event Repair Issues

**Problem:** Birthday events not being repaired
```
Calendar Repairer failed for automation: Permission denied
```

**Solutions:**
1. Check calendar is not read-only:
   ```yaml
   calendars:
     - id: "automation"
       read_only: false  # Must be false for repairs
   ```

2. Verify ETag handling:
   ```yaml
   caldav:
     write:
       if_match: false  # Disable ETag for testing
   ```

### Performance Issues

**Problem:** Slow sync with many events

**Solutions:**
1. Enable sync-collection:
   ```yaml
   caldav:
     sync:
       use_sync_collection: true
   ```

2. Increase parallel requests:
   ```yaml
   caldav:
     sync:
       parallel_requests: 5
   ```

3. Reduce sync window:
   ```yaml
   caldav:
     sync:
       window_days: 90
   ```

## Best Practices

### 1. Network Configuration
- Use local network for CalDAV server
- Consider VPN/WireGuard for remote access
- Enable TLS for production deployments

### 2. Calendar Organization
- Use separate calendars for different event types
- Mark calendars read-only if they shouldn't be modified
- Set appropriate timezones for each calendar

### 3. Performance Optimization
- Enable sync-collection for efficient incremental sync
- Use appropriate sync intervals (1-24 hours)
- Monitor sync performance and adjust parallel requests

### 4. Backup and Recovery
- Regular backup of CalDAV server data
- Export important events using the API
- Test restore procedures

### 5. Monitoring
- Monitor CalDAV server health
- Check Chronos backend status regularly
- Set up alerts for sync failures

## Advanced Configuration

### Custom Repair Rules

CalDAV events support the same repair rules as Google Calendar:

```yaml
repair_and_enrich:
  rules:
    - id: "anniversary"
      keywords: ["ANNIV", "ANNIVERSARY"]
      title_template: "🎖️ {label}: {name_or_label} since {date_display}{years_since_suffix}"
      all_day: true
      rrule: "FREQ=YEARLY"
      enrich:
        event_type: "anniversary"
        tags: ["anniversary"]
```

### Multi-Server Setup

Configure multiple Radicale servers:

```yaml
caldav:
  calendars:
    - id: "work-calendar"
      url: "http://work-server:5232/user/calendar/"
    - id: "personal-calendar"
      url: "http://home-server:5232/user/calendar/"
```

### Custom Authentication

For advanced authentication scenarios:

```yaml
caldav:
  auth:
    mode: "custom"
    headers:
      Authorization: "Bearer custom-token"
      X-Custom-Auth: "value"
```

## Support

For additional help:
- Check the [API Documentation](API_Reference.md)
- Review [Configuration Examples](config_examples/)
- Submit issues on [GitHub](https://github.com/your-repo/chronos)

## Changelog

### v2.1 - CalDAV Integration
- ✅ CalDAV/Radicale as default backend
- ✅ SourceAdapter unified interface
- ✅ RFC 6578 sync-collection support
- ✅ X-CHRONOS-* idempotency markers
- ✅ Backend-agnostic calendar repair
- ✅ CalDAV REST API endpoints
- ✅ Comprehensive test suite