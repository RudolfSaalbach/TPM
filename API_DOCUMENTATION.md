# Chronos Engine v2.2 - Complete API Documentation

## Overview

Chronos Engine v2.2 provides a comprehensive RESTful API for time management, event scheduling, and automation. This documentation covers all endpoints, including new v2.2 features for sub-tasks, event linking, availability checking, and workflow automation.

**Base URL**: `http://localhost:8000` (configurable)
**API Version**: v2.2
**Authentication**: Bearer token via `Authorization` header

## Authentication

All API endpoints require authentication using a Bearer token:

```http
Authorization: Bearer your-api-key-here
```

The API key is configured in `chronos.yaml`:

```yaml
api:
  api_key: "your-secure-production-api-key"
```

## Core Event Management

### Events

#### List All Events

```http
GET /api/v1/events
```

**Query Parameters:**
- `skip` (int, optional): Number of events to skip (default: 0)
- `limit` (int, optional): Maximum number of events to return (default: 100)
- `status` (string, optional): Filter by event status (`scheduled`, `in_progress`, `completed`, `cancelled`)
- `priority` (string, optional): Filter by priority (`low`, `medium`, `high`, `urgent`)
- `event_type` (string, optional): Filter by type (`task`, `meeting`, `deadline`, `reminder`)

**Response:**
```json
{
  "events": [
    {
      "id": "event-123",
      "title": "Team Meeting",
      "description": "Weekly team sync",
      "start_time": "2025-01-20T10:00:00Z",
      "end_time": "2025-01-20T11:00:00Z",
      "priority": "high",
      "event_type": "meeting",
      "status": "scheduled",
      "attendees": ["alice@company.com", "bob@company.com"],
      "location": "Conference Room A",
      "tags": ["weekly", "team"],
      "calendar_id": "primary",
      "sub_tasks": [
        {
          "id": "task-1",
          "text": "Review agenda",
          "completed": false,
          "created_at": "2025-01-20T09:00:00Z",
          "completed_at": null
        }
      ],
      "created_at": "2025-01-20T08:00:00Z",
      "updated_at": "2025-01-20T09:30:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

#### Get Event by ID

```http
GET /api/v1/events/{event_id}
```

**Path Parameters:**
- `event_id` (string): Unique event identifier

**Response:** Single event object (same structure as list response)

#### Create Event

```http
POST /api/v1/events
```

**Request Body:**
```json
{
  "title": "New Project Meeting",
  "description": "Kickoff meeting for new project",
  "start_time": "2025-01-22T14:00:00Z",
  "end_time": "2025-01-22T15:30:00Z",
  "priority": "high",
  "event_type": "meeting",
  "status": "scheduled",
  "attendees": ["team@company.com"],
  "location": "Room B",
  "tags": ["project", "kickoff"],
  "sub_tasks": [
    {
      "text": "Prepare project overview",
      "completed": false
    },
    {
      "text": "Send calendar invites",
      "completed": true
    }
  ]
}
```

**Response:** Created event object with generated ID

#### Update Event

```http
PUT /api/v1/events/{event_id}
```

**Request Body:** Same as create, all fields optional

**Response:** Updated event object

#### Delete Event

```http
DELETE /api/v1/events/{event_id}
```

**Response:** `204 No Content`

## v2.2 New Features

### Sub-tasks Management

#### Get Event Sub-tasks

```http
GET /api/v2.2/events/{event_id}/sub-tasks
```

**Response:**
```json
{
  "sub_tasks": [
    {
      "id": "task-1",
      "text": "Complete requirements analysis",
      "completed": false,
      "created_at": "2025-01-20T10:00:00Z",
      "completed_at": null
    },
    {
      "id": "task-2",
      "text": "Review design mockups",
      "completed": true,
      "created_at": "2025-01-20T10:00:00Z",
      "completed_at": "2025-01-20T11:30:00Z"
    }
  ]
}
```

#### Add Sub-task to Event

```http
POST /api/v2.2/events/{event_id}/sub-tasks
```

**Request Body:**
```json
{
  "text": "New task to complete",
  "completed": false
}
```

**Response:** Created sub-task object

#### Update Sub-task

```http
PUT /api/v2.2/events/{event_id}/sub-tasks/{task_id}
```

**Request Body:**
```json
{
  "text": "Updated task description",
  "completed": true
}
```

**Response:** Updated sub-task object

#### Delete Sub-task

```http
DELETE /api/v2.2/events/{event_id}/sub-tasks/{task_id}
```

**Response:** `204 No Content`

### Event Linking

#### Get Event Links

```http
GET /api/v2.2/event-links
```

**Query Parameters:**
- `source_event_id` (string, optional): Filter by source event
- `target_event_id` (string, optional): Filter by target event
- `link_type` (string, optional): Filter by link type

**Response:**
```json
{
  "links": [
    {
      "id": "link-123",
      "source_event_id": "event-1",
      "target_event_id": "event-2",
      "link_type": "depends_on",
      "created_at": "2025-01-20T10:00:00Z"
    }
  ]
}
```

**Link Types:**
- `related` - General relationship
- `depends_on` - Source depends on target
- `blocks` - Source blocks target
- `child_of` - Source is child of target
- `follows` - Source follows target
- `references` - Source references target

#### Create Event Link

```http
POST /api/v2.2/event-links
```

**Request Body:**
```json
{
  "source_event_id": "event-1",
  "target_event_id": "event-2",
  "link_type": "depends_on"
}
```

**Response:** Created link object

#### Delete Event Link

```http
DELETE /api/v2.2/event-links/{link_id}
```

**Response:** `204 No Content`

### Availability Checking

#### Check Availability

```http
POST /api/v2.2/availability/check
```

**Request Body:**
```json
{
  "start_time": "2025-01-22T09:00:00Z",
  "end_time": "2025-01-22T17:00:00Z",
  "attendees": ["alice@company.com", "bob@company.com"],
  "calendar_ids": ["primary", "work"]
}
```

**Response:**
```json
{
  "availability": [
    {
      "start_time": "2025-01-22T09:00:00Z",
      "end_time": "2025-01-22T10:00:00Z",
      "available": true,
      "conflicts": []
    },
    {
      "start_time": "2025-01-22T10:00:00Z",
      "end_time": "2025-01-22T11:00:00Z",
      "available": false,
      "conflicts": ["Team Standup", "Code Review"]
    }
  ]
}
```

#### Find Free Slots

```http
POST /api/v2.2/availability/free-slots
```

**Request Body:**
```json
{
  "start_time": "2025-01-22T09:00:00Z",
  "end_time": "2025-01-22T17:00:00Z",
  "duration_minutes": 60,
  "attendees": ["alice@company.com"],
  "calendar_ids": ["primary"]
}
```

**Response:**
```json
{
  "free_slots": [
    {
      "start_time": "2025-01-22T11:00:00Z",
      "end_time": "2025-01-22T12:00:00Z",
      "duration_minutes": 60
    },
    {
      "start_time": "2025-01-22T14:00:00Z",
      "end_time": "2025-01-22T15:00:00Z",
      "duration_minutes": 60
    }
  ]
}
```

### Workflow Automation

#### List Workflows

```http
GET /api/v2.2/workflows
```

**Response:**
```json
{
  "workflows": [
    {
      "id": "workflow-1",
      "trigger_command": "DEPLOY",
      "trigger_system": "production",
      "follow_up_command": "STATUS_CHECK",
      "follow_up_system": "monitoring",
      "follow_up_params": {
        "timeout": 300,
        "retries": 3
      },
      "delay_seconds": 30,
      "created_at": "2025-01-20T10:00:00Z"
    }
  ]
}
```

#### Create Workflow

```http
POST /api/v2.2/workflows
```

**Request Body:**
```json
{
  "trigger_command": "BACKUP",
  "trigger_system": "database",
  "follow_up_command": "SEND_NOTIFICATION",
  "follow_up_system": "alerts",
  "follow_up_params": {
    "message": "Backup completed",
    "channels": ["email", "slack"]
  },
  "delay_seconds": 0
}
```

**Response:** Created workflow object

#### Delete Workflow

```http
DELETE /api/v2.2/workflows/{workflow_id}
```

**Response:** `204 No Content`

### Command Polling

#### Poll for Commands

```http
GET /api/v2.2/commands/poll/{system_name}
```

**Path Parameters:**
- `system_name` (string): Name of the system requesting commands

**Response:**
```json
{
  "commands": [
    {
      "id": "cmd-1",
      "command": "DEPLOY",
      "system": "production",
      "params": {
        "environment": "prod",
        "version": "v2.2.0"
      },
      "created_at": "2025-01-20T10:00:00Z"
    }
  ]
}
```

#### Mark Command Complete

```http
POST /api/v2.2/commands/{command_id}/complete
```

**Request Body:**
```json
{
  "status": "success",
  "output": "Deployment completed successfully",
  "completed_at": "2025-01-20T10:05:00Z"
}
```

**Response:** `200 OK`

#### Mark Command Failed

```http
POST /api/v2.2/commands/{command_id}/failed
```

**Request Body:**
```json
{
  "status": "failed",
  "error": "Connection timeout",
  "completed_at": "2025-01-20T10:03:00Z"
}
```

**Response:** `200 OK`

## System Endpoints

### Health Check

```http
GET /api/v1/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "2.2.0",
  "database": "connected",
  "plugins": {
    "command_handler": "active",
    "undefined_guard": "active"
  },
  "timestamp": "2025-01-20T10:00:00Z"
}
```

### System Status

```http
GET /api/v1/status
```

**Response:**
```json
{
  "version": "2.2.0",
  "uptime": "2 days, 14:30:22",
  "events_count": 1247,
  "active_workflows": 12,
  "last_backup": "2025-01-20T02:00:00Z",
  "memory_usage": "145.2 MB",
  "cpu_usage": "2.3%"
}
```

## Error Responses

All endpoints return consistent error responses:

### 400 Bad Request
```json
{
  "error": "validation_error",
  "message": "Invalid input data",
  "details": {
    "field": "start_time",
    "issue": "start_time must be before end_time"
  }
}
```

### 401 Unauthorized
```json
{
  "error": "unauthorized",
  "message": "Invalid or missing API key"
}
```

### 404 Not Found
```json
{
  "error": "not_found",
  "message": "Event not found",
  "resource_id": "event-123"
}
```

### 409 Conflict
```json
{
  "error": "conflict",
  "message": "Event link already exists",
  "details": {
    "source_event_id": "event-1",
    "target_event_id": "event-2"
  }
}
```

### 500 Internal Server Error
```json
{
  "error": "internal_error",
  "message": "An unexpected error occurred",
  "request_id": "req-abc123"
}
```

## Rate Limiting

API requests are rate limited based on configuration:

**Default Limits:**
- 100 requests per minute per API key
- 1000 requests per hour per API key

**Headers:**
- `X-RateLimit-Limit`: Current rate limit
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Time when limit resets (Unix timestamp)

**Rate Limit Exceeded (429):**
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after": 60
}
```

## SDK Examples

### Python

```python
import requests
from datetime import datetime, timedelta

class ChronosClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def create_event(self, title, start_time, end_time, **kwargs):
        data = {
            "title": title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            **kwargs
        }
        response = requests.post(
            f"{self.base_url}/api/v1/events",
            json=data,
            headers=self.headers
        )
        return response.json()

    def add_sub_task(self, event_id, text, completed=False):
        data = {"text": text, "completed": completed}
        response = requests.post(
            f"{self.base_url}/api/v2.2/events/{event_id}/sub-tasks",
            json=data,
            headers=self.headers
        )
        return response.json()

    def create_event_link(self, source_id, target_id, link_type):
        data = {
            "source_event_id": source_id,
            "target_event_id": target_id,
            "link_type": link_type
        }
        response = requests.post(
            f"{self.base_url}/api/v2.2/event-links",
            json=data,
            headers=self.headers
        )
        return response.json()

# Usage example
client = ChronosClient("http://localhost:8000", "your-api-key")

# Create event with sub-tasks
event = client.create_event(
    title="Project Planning",
    start_time=datetime.now(),
    end_time=datetime.now() + timedelta(hours=2),
    sub_tasks=[
        {"text": "Review requirements", "completed": False},
        {"text": "Create timeline", "completed": False}
    ]
)

# Link events
client.create_event_link(event["id"], "follow-up-123", "leads_to")
```

### JavaScript

```javascript
class ChronosClient {
    constructor(baseUrl, apiKey) {
        this.baseUrl = baseUrl;
        this.headers = {
            'Authorization': `Bearer ${apiKey}`,
            'Content-Type': 'application/json'
        };
    }

    async createEvent(eventData) {
        const response = await fetch(`${this.baseUrl}/api/v1/events`, {
            method: 'POST',
            headers: this.headers,
            body: JSON.stringify(eventData)
        });
        return response.json();
    }

    async checkAvailability(request) {
        const response = await fetch(`${this.baseUrl}/api/v2.2/availability/check`, {
            method: 'POST',
            headers: this.headers,
            body: JSON.stringify(request)
        });
        return response.json();
    }

    async pollCommands(systemName) {
        const response = await fetch(`${this.baseUrl}/api/v2.2/commands/poll/${systemName}`, {
            headers: this.headers
        });
        return response.json();
    }
}

// Usage example
const client = new ChronosClient('http://localhost:8000', 'your-api-key');

// Create event
const event = await client.createEvent({
    title: 'Team Meeting',
    start_time: '2025-01-22T10:00:00Z',
    end_time: '2025-01-22T11:00:00Z',
    attendees: ['team@company.com']
});

// Check availability
const availability = await client.checkAvailability({
    start_time: '2025-01-22T09:00:00Z',
    end_time: '2025-01-22T17:00:00Z',
    attendees: ['alice@company.com', 'bob@company.com']
});
```

## OpenAPI Specification

The complete OpenAPI 3.0 specification is available at:

```http
GET /api/docs
```

Interactive API documentation (Swagger UI) is available at:

```http
GET /docs
```

Alternative documentation (ReDoc) is available at:

```http
GET /redoc
```

---

**API Version**: v2.2
**Last Updated**: 2025-01-20
**Support**: Check logs at `./logs/chronos.log` for debugging