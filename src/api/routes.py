"""
Updated API routes with transactional atomicity.
Only showing the modified create_event and update_event endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import Dict, Any
import uuid
import logging

from src.core.transaction_manager import TransactionManager
from src.database.models import Event
from src.api.schemas import EventCreate, EventUpdate, EventResponse
from src.api.exceptions import (
    ValidationError,
    CalendarSyncError,
    EventNotFoundError,
    handle_api_errors
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
@handle_api_errors
async def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
    calendar_client = Depends(get_calendar_client)
) -> EventResponse:
    """
    Create a new event with transactional consistency.
    Ensures both database and Google Calendar are updated atomically.
    """
    transaction_id = str(uuid.uuid4())
    transaction_manager = TransactionManager(db, calendar_client)
    
    # Prepare database operation
    def db_operation(event_dict):
        new_event = Event(**event_dict)
        db.add(new_event)
        db.flush()  # Get the ID without committing
        return new_event
    
    # Prepare API operation
    def api_operation(calendar_event):
        return calendar_client.events().insert(
            calendarId='primary',
            body=calendar_event
        ).execute()
    
    # Prepare arguments
    event_dict = event_data.dict()
    event_dict['id'] = transaction_id  # Use transaction ID as event ID
    
    calendar_event = {
        'summary': event_data.title,
        'description': event_data.description,
        'start': {'dateTime': event_data.start_time.isoformat()},
        'end': {'dateTime': event_data.end_time.isoformat()},
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }
    
    # Execute transaction
    success, result, error = transaction_manager.execute_transaction(
        db_operation=db_operation,
        api_operation=api_operation,
        transaction_id=transaction_id,
        operation_name="create_event",
        db_args={"event_dict": event_dict},
        api_args={"calendar_event": calendar_event}
    )
    
    if success:
        logger.info(f"Event {transaction_id} created successfully")
        return EventResponse.from_orm(result["db"])
    else:
        if "API operation failed" in error:
            raise CalendarSyncError(
                detail="Event saved locally but calendar sync failed. It will be retried automatically.",
                transaction_id=transaction_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error
            )


@router.put("/events/{event_id}", response_model=EventResponse)
@handle_api_errors
async def update_event(
    event_id: str,
    event_update: EventUpdate,
    db: Session = Depends(get_db),
    calendar_client = Depends(get_calendar_client)
) -> EventResponse:
    """
    Update an event with transactional consistency.
    """
    transaction_id = str(uuid.uuid4())
    transaction_manager = TransactionManager(db, calendar_client)
    
    # Check if event exists
    existing_event = db.query(Event).filter(Event.id == event_id).first()
    if not existing_event:
        raise EventNotFoundError(event_id=event_id)
    
    # Prepare database operation
    def db_operation(event_id, updates):
        event = db.query(Event).filter(Event.id == event_id).first()
        for key, value in updates.items():
            if value is not None:
                setattr(event, key, value)
        db.flush()
        return event
    
    # Prepare API operation
    def api_operation(event_id, calendar_updates):
        return calendar_client.events().patch(
            calendarId='primary',
            eventId=event_id,
            body=calendar_updates
        ).execute()
    
    # Prepare arguments
    updates = event_update.dict(exclude_unset=True)
    
    calendar_updates = {}
    if 'title' in updates:
        calendar_updates['summary'] = updates['title']
    if 'description' in updates:
        calendar_updates['description'] = updates['description']
    if 'start_time' in updates:
        calendar_updates['start'] = {'dateTime': updates['start_time'].isoformat()}
    if 'end_time' in updates:
        calendar_updates['end'] = {'dateTime': updates['end_time'].isoformat()}
    
    # Execute transaction
    success, result, error = transaction_manager.execute_transaction(
        db_operation=db_operation,
        api_operation=api_operation,
        transaction_id=transaction_id,
        operation_name="update_event",
        db_args={"event_id": event_id, "updates": updates},
        api_args={"event_id": event_id, "calendar_updates": calendar_updates}
    )
    
    if success:
        logger.info(f"Event {event_id} updated successfully")
        return EventResponse.from_orm(result["db"])
    else:
        if "API operation failed" in error:
            raise CalendarSyncError(
                detail="Event updated locally but calendar sync failed. It will be retried automatically.",
                transaction_id=transaction_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error
            )
