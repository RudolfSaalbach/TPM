#!/usr/bin/env python3
"""TEMPORARY API TEST - COMPLETE API FOR CREATE EVENT MODAL"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from datetime import datetime
from typing import Optional, List

app = FastAPI()

# Event Model for creation
class EventCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    start_time: str
    end_time: str
    calendar: str
    template_id: Optional[str] = None

@app.get("/api/v1/sync/health")
async def health_check():
    """Direct health check - no validation"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.1-FIXED"
    }

@app.get("/api/v1/events")
async def get_events():
    """Direct events endpoint"""
    return {
        "success": True,
        "events": [],
        "total": 0,
        "message": "API VALIDATION BYPASSED - WORKING"
    }

@app.get("/api/v1/templates")
async def get_templates():
    """Templates endpoint for Create Event Modal"""
    return {
        "success": True,
        "templates": [
            {
                "id": "meeting",
                "name": "Meeting",
                "description": "Standard meeting template",
                "default_duration": 60,
                "defaults": {
                    "title": "Meeting",
                    "description": "Meeting description"
                }
            },
            {
                "id": "appointment",
                "name": "Termin",
                "description": "Personal appointment",
                "default_duration": 30,
                "defaults": {
                    "title": "Termin",
                    "description": "Personal appointment"
                }
            },
            {
                "id": "task",
                "name": "Aufgabe",
                "description": "Task or todo item",
                "default_duration": 120,
                "defaults": {
                    "title": "Aufgabe",
                    "description": "Task description"
                }
            }
        ]
    }

@app.get("/api/v1/caldav/calendars")
async def get_calendars():
    """Calendars endpoint for Create Event Modal"""
    return {
        "success": True,
        "calendars": [
            {
                "id": "automation",
                "name": "Automation",
                "description": "Automation calendar",
                "alias": "automation",
                "color": "#FF6B6B"
            },
            {
                "id": "dates",
                "name": "Dates",
                "description": "Important dates",
                "alias": "dates",
                "color": "#4ECDC4"
            },
            {
                "id": "special",
                "name": "Special",
                "description": "Special events",
                "alias": "special",
                "color": "#45B7D1"
            }
        ]
    }

@app.post("/api/v1/events")
async def create_event(event: EventCreate):
    """Create new event endpoint"""
    return {
        "success": True,
        "event": {
            "id": f"evt_{datetime.now().timestamp()}",
            "title": event.title,
            "description": event.description,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "calendar": event.calendar,
            "template_id": event.template_id,
            "created": datetime.utcnow().isoformat()
        },
        "message": "Event created successfully"
    }

@app.post("/api/v1/sync")
async def sync_calendar():
    """Calendar sync endpoint"""
    return {
        "success": True,
        "message": "Calendar sync completed",
        "events_synced": 3,
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)