# CalDAV API Reference

## Overview

This document describes the CalDAV-specific REST API endpoints added in Chronos Engine v2.1. These endpoints provide comprehensive management of CalDAV backends, calendars, and events.

## Authentication

All CalDAV API endpoints require authentication via API key:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8080/caldav/...
```

## Backend Management

### Get Backend Information

Get detailed information about the current CalDAV backend.

**Endpoint:** `GET /caldav/backend/info`

**Response:**
```json
{
  "success": true,
  "backend_info": {
    "type": "caldav",
    "capabilities": {
      "name": "CalDAV/Radicale",
      "can_write": true,
      "supports_sync_token": true,
      "timezone": "Europe/Berlin"
    },
    "calendars": [
      {
        "id": "automation",
        "alias": "Automation",
        "read_only": false,
        "timezone": "Europe/Berlin"
      }
    ],
    "connection_valid": true
  },
  "timestamp": "2025-01-15T10:00:00"
}
```

**Status Codes:**
- `200` - Success
- `401` - Invalid API key
- `503` - Source manager not available

---

### Test Backend Connection

Test the connection to the CalDAV backend.

**Endpoint:** `POST /caldav/connection/test`

**Response:**
```json
{
  "success": true,
  "connection_valid": true,
  "backend_type": "caldav",
  "calendars_available": 3,
  "test_timestamp": "2025-01-15T10:00:00"
}
```

**Status Codes:**
- `200` - Test completed (check `connection_valid` for result)
- `401` - Invalid API key
- `503` - Source manager not available

---

### Switch Backend

Switch between CalDAV and Google Calendar backends.

**Endpoint:** `POST /caldav/backend/switch`

**Request Body:**
```json
{
  "backend_type": "google",
  "config": {
    "google": {
      "enabled": true,
      "credentials_file": "config/credentials.json",
      "token_file": "config/token.json"
    }
  }
}
```

**Parameters:**
- `backend_type` (required): `"caldav"` or `"google"`
- `config` (optional): New configuration for the backend

**Response:**
```json
{
  "success": true,
  "switched_to": "google",
  "backend_info": {
    "type": "google",
    "capabilities": { ... },
    "calendars": [ ... ]
  },
  "switched_at": "2025-01-15T10:00:00"
}
```

**Status Codes:**
- `200` - Switch successful
- `400` - Invalid backend type
- `401` - Invalid API key
- `500` - Switch failed
- `503` - Source manager not available

## Calendar Management

### List Calendars

Get all available CalDAV calendars.

**Endpoint:** `GET /caldav/calendars`

**Response:**
```json
{
  "success": true,
  "calendars": [
    {
      "id": "automation",
      "alias": "Automation",
      "url": "http://10.210.1.1:5232/radicaleuser/automation/",
      "read_only": false,
      "timezone": "Europe/Berlin"
    },
    {
      "id": "dates",
      "alias": "Dates",
      "url": "http://10.210.1.1:5232/radicaleuser/dates/",
      "read_only": false,
      "timezone": "Europe/Berlin"
    },
    {
      "id": "special",
      "alias": "Special",
      "url": "http://10.210.1.1:5232/radicaleuser/special/",
      "read_only": true,
      "timezone": "Europe/Berlin"
    }
  ],
  "count": 3,
  "timestamp": "2025-01-15T10:00:00"
}
```

**Status Codes:**
- `200` - Success
- `401` - Invalid API key
- `503` - Source manager not available

---

### Sync Calendar

Manually trigger synchronization for a specific calendar.

**Endpoint:** `POST /caldav/calendars/{calendar_id}/sync`

**Query Parameters:**
- `days_ahead` (optional, default: 7): Number of days to sync ahead
- `force_refresh` (optional, default: false): Force full refresh instead of incremental sync

**Example:**
```bash
POST /caldav/calendars/automation/sync?days_ahead=30&force_refresh=false
```

**Response:**
```json
{
  "success": true,
  "calendar_id": "automation",
  "calendar_alias": "Automation",
  "events_fetched": 25,
  "sync_token": "sync-token-123456",
  "next_page_token": null,
  "time_window": {
    "since": "2025-01-15T10:00:00",
    "until": "2025-02-14T10:00:00"
  },
  "timestamp": "2025-01-15T10:00:00"
}
```

**Status Codes:**
- `200` - Sync completed
- `401` - Invalid API key
- `404` - Calendar not found
- `500` - Sync failed
- `503` - Source manager not available

## Event Operations

### Create Event

Create a new event in a CalDAV calendar.

**Endpoint:** `POST /caldav/calendars/{calendar_id}/events`

**Request Body:**
```json
{
  "summary": "New CalDAV Event",
  "description": "Event created via API",
  "start_time": "2025-01-15T14:00:00",
  "end_time": "2025-01-15T15:00:00",
  "all_day": false,
  "timezone": "Europe/Berlin",
  "rrule": "FREQ=WEEKLY",
  "chronos_markers": {
    "cleaned": "true",
    "rule_id": "manual"
  }
}
```

**Required Fields:**
- `summary`: Event title

**Optional Fields:**
- `description`: Event description
- `start_time`: Start time (ISO format)
- `end_time`: End time (ISO format)
- `all_day`: All-day event flag
- `timezone`: Event timezone
- `rrule`: Recurrence rule
- `chronos_markers`: Idempotency markers

**Response:**
```json
{
  "success": true,
  "event_id": "new-event-uuid-123",
  "calendar_id": "automation",
  "calendar_alias": "Automation",
  "created_at": "2025-01-15T14:00:00"
}
```

**Status Codes:**
- `200` - Event created
- `400` - Invalid event data
- `401` - Invalid API key
- `403` - Calendar is read-only
- `404` - Calendar not found
- `500` - Creation failed

---

### Get Event

Retrieve a specific event from a CalDAV calendar.

**Endpoint:** `GET /caldav/calendars/{calendar_id}/events/{event_id}`

**Response:**
```json
{
  "success": true,
  "event": {
    "id": "event-123",
    "uid": "event-123",
    "summary": "CalDAV Event",
    "description": "Event from CalDAV",
    "start_time": "2025-01-15T14:00:00",
    "end_time": "2025-01-15T15:00:00",
    "all_day": false,
    "calendar_id": "automation",
    "etag": "\"etag-123\"",
    "rrule": null,
    "recurrence_id": null,
    "is_series_master": false,
    "timezone": "Europe/Berlin",
    "meta": {
      "chronos_markers": {
        "cleaned": "true",
        "rule_id": "bday"
      }
    }
  },
  "calendar_id": "automation",
  "calendar_alias": "Automation",
  "timestamp": "2025-01-15T10:00:00"
}
```

**Status Codes:**
- `200` - Event found
- `401` - Invalid API key
- `404` - Calendar or event not found
- `500` - Retrieval failed

---

### Update Event

Update an existing event in a CalDAV calendar.

**Endpoint:** `PATCH /caldav/calendars/{calendar_id}/events/{event_id}`

**Headers:**
- `If-Match` (optional): ETag for conflict detection

**Request Body:**
```json
{
  "summary": "Updated Event Title",
  "description": "Updated description",
  "start_time": "2025-01-15T15:00:00",
  "end_time": "2025-01-15T16:00:00"
}
```

**Response:**
```json
{
  "success": true,
  "event_id": "event-123",
  "calendar_id": "automation",
  "calendar_alias": "Automation",
  "new_etag": "\"new-etag-456\"",
  "patched_at": "2025-01-15T14:30:00"
}
```

**Status Codes:**
- `200` - Event updated
- `401` - Invalid API key
- `403` - Calendar is read-only
- `404` - Calendar or event not found
- `409` - ETag conflict
- `500` - Update failed

---

### Delete Event

Delete an event from a CalDAV calendar.

**Endpoint:** `DELETE /caldav/calendars/{calendar_id}/events/{event_id}`

**Response:**
```json
{
  "success": true,
  "event_id": "event-123",
  "calendar_id": "automation",
  "calendar_alias": "Automation",
  "deleted_at": "2025-01-15T14:30:00"
}
```

**Status Codes:**
- `200` - Event deleted
- `401` - Invalid API key
- `403` - Calendar is read-only
- `404` - Calendar or event not found
- `500` - Deletion failed

## Error Responses

All endpoints return standardized error responses:

```json
{
  "detail": "Error description"
}
```

### Common Error Codes

- **400 Bad Request**: Invalid request data
  ```json
  {
    "detail": "Event summary is required"
  }
  ```

- **401 Unauthorized**: Invalid API key
  ```json
  {
    "detail": "Invalid API key. Please ensure you're using the correct X-API-Key header."
  }
  ```

- **403 Forbidden**: Permission denied
  ```json
  {
    "detail": "Calendar Automation is read-only"
  }
  ```

- **404 Not Found**: Resource not found
  ```json
  {
    "detail": "Calendar automation not found"
  }
  ```

- **409 Conflict**: ETag conflict
  ```json
  {
    "detail": "ETag conflict during patch"
  }
  ```

- **500 Internal Server Error**: Server error
  ```json
  {
    "detail": "Failed to create event: Connection timeout"
  }
  ```

- **503 Service Unavailable**: Service not available
  ```json
  {
    "detail": "Calendar source manager not available"
  }
  ```

## Examples

### Complete Event Management Workflow

```bash
# 1. List available calendars
curl -H "X-API-Key: your-api-key" \
  http://localhost:8080/caldav/calendars

# 2. Create a new event
curl -X POST -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Team Meeting",
    "description": "Weekly team sync",
    "start_time": "2025-01-20T14:00:00",
    "end_time": "2025-01-20T15:00:00",
    "all_day": false
  }' \
  http://localhost:8080/caldav/calendars/automation/events

# 3. Get the created event
curl -H "X-API-Key: your-api-key" \
  http://localhost:8080/caldav/calendars/automation/events/new-event-123

# 4. Update the event
curl -X PATCH -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -H "If-Match: \"etag-123\"" \
  -d '{
    "summary": "Updated Team Meeting",
    "start_time": "2025-01-20T15:00:00"
  }' \
  http://localhost:8080/caldav/calendars/automation/events/new-event-123

# 5. Delete the event
curl -X DELETE -H "X-API-Key: your-api-key" \
  http://localhost:8080/caldav/calendars/automation/events/new-event-123
```

### Backend Switching

```bash
# Switch to Google Calendar
curl -X POST -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "backend_type": "google",
    "config": {
      "google": {
        "enabled": true,
        "credentials_file": "config/credentials.json"
      }
    }
  }' \
  http://localhost:8080/caldav/backend/switch

# Switch back to CalDAV
curl -X POST -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "backend_type": "caldav"
  }' \
  http://localhost:8080/caldav/backend/switch
```

### Bulk Calendar Sync

```bash
# Get all calendars
CALENDARS=$(curl -s -H "X-API-Key: your-api-key" \
  http://localhost:8080/caldav/calendars | jq -r '.calendars[].id')

# Sync each calendar
for calendar in $CALENDARS; do
  echo "Syncing calendar: $calendar"
  curl -X POST -H "X-API-Key: your-api-key" \
    "http://localhost:8080/caldav/calendars/$calendar/sync?days_ahead=30"
done
```

## Rate Limiting

- **Default Limit**: 100 requests per minute per API key
- **Burst Limit**: 10 requests per second
- **Headers**: Rate limit information in response headers:
  ```
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 95
  X-RateLimit-Reset: 1642694400
  ```

## Webhook Support

CalDAV events can trigger webhooks for external integration:

```yaml
# Configuration
webhooks:
  caldav_events:
    url: "https://your-webhook-endpoint.com/caldav"
    events: ["event.created", "event.updated", "event.deleted"]
    secret: "webhook-secret"
```

**Webhook Payload:**
```json
{
  "event": "event.created",
  "calendar_id": "automation",
  "event_id": "new-event-123",
  "timestamp": "2025-01-15T14:00:00",
  "data": {
    "summary": "New Event",
    "start_time": "2025-01-20T14:00:00"
  }
}
```

## SDK Examples

### Python

```python
import requests

class CalDAVClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}

    def list_calendars(self):
        response = requests.get(
            f"{self.base_url}/caldav/calendars",
            headers=self.headers
        )
        return response.json()

    def create_event(self, calendar_id, event_data):
        response = requests.post(
            f"{self.base_url}/caldav/calendars/{calendar_id}/events",
            headers=self.headers,
            json=event_data
        )
        return response.json()

# Usage
client = CalDAVClient("http://localhost:8080", "your-api-key")
calendars = client.list_calendars()
print(f"Found {calendars['count']} calendars")
```

### JavaScript

```javascript
class CalDAVClient {
    constructor(baseUrl, apiKey) {
        this.baseUrl = baseUrl;
        this.headers = { 'X-API-Key': apiKey };
    }

    async listCalendars() {
        const response = await fetch(`${this.baseUrl}/caldav/calendars`, {
            headers: this.headers
        });
        return response.json();
    }

    async createEvent(calendarId, eventData) {
        const response = await fetch(
            `${this.baseUrl}/caldav/calendars/${calendarId}/events`,
            {
                method: 'POST',
                headers: { ...this.headers, 'Content-Type': 'application/json' },
                body: JSON.stringify(eventData)
            }
        );
        return response.json();
    }
}

// Usage
const client = new CalDAVClient('http://localhost:8080', 'your-api-key');
const calendars = await client.listCalendars();
console.log(`Found ${calendars.count} calendars`);
```

## OpenAPI Specification

The complete OpenAPI specification is available at:
- **JSON**: `GET /openapi.json`
- **Interactive Docs**: `GET /docs`
- **ReDoc**: `GET /redoc`