"""
Event parser for converting calendar events to ChronosEvent objects
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import zoneinfo

from src.core.models import ChronosEvent, Priority, EventType, EventStatus, SubTask


class EventParser:
    """Parse calendar events into structured ChronosEvent objects"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Priority keywords for automatic detection
        self.priority_keywords = {
            Priority.URGENT: ['urgent', 'asap', 'emergency', 'critical'],
            Priority.HIGH: ['high priority', 'important', 'deadline', 'due soon', 'pressing'],
            Priority.MEDIUM: ['medium priority', 'normal', 'regular'],
            Priority.LOW: ['low priority', 'optional', 'sometime', 'later', 'casual']
        }
        
        # Event type keywords
        self.type_keywords = {
            EventType.MEETING: ['meeting', 'call', 'conference', 'discussion', 'sync'],
            EventType.TASK: ['task', 'work', 'do', 'complete', 'finish'],
            EventType.APPOINTMENT: ['appointment', 'visit', 'consultation'],
            EventType.REMINDER: ['reminder', 'note', 'remember'],
            EventType.BLOCK: ['block', 'focus', 'deep work', 'concentration']
        }
    
    def parse_event(self, calendar_event: Dict[str, Any]) -> ChronosEvent:
        """Parse a calendar event into a ChronosEvent object"""
        
        try:
            # Extract basic information
            event_id = calendar_event.get('id', '')
            title = calendar_event.get('summary', 'Untitled Event')
            description = calendar_event.get('description', '')
            location = calendar_event.get('location', '')
            
            # Parse datetime information
            start_time = self._parse_datetime(calendar_event.get('start'))
            end_time = self._parse_datetime(calendar_event.get('end'))
            
            # Extract attendees
            attendees = []
            for attendee in calendar_event.get('attendees', []):
                if 'email' in attendee:
                    attendees.append(attendee['email'])
            
            # Determine priority and type from content
            priority = self._detect_priority(title, description)
            event_type = self._detect_event_type(title, description)
            
            # Extract tags from description
            tags = self._extract_tags(description)

            # Parse sub-tasks from description (v2.2 feature)
            sub_tasks = self._parse_sub_tasks(description)

            # Calculate estimated duration
            estimated_duration = None
            if start_time and end_time:
                estimated_duration = end_time - start_time
            
            # Create ChronosEvent
            chronos_event = ChronosEvent(
                id=event_id,
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                priority=priority,
                event_type=event_type,
                status=EventStatus.SCHEDULED,
                calendar_id=calendar_event.get('organizer', {}).get('email', ''),
                attendees=attendees,
                location=location,
                tags=tags,
                estimated_duration=estimated_duration,
                sub_tasks=sub_tasks
            )
            
            self.logger.debug(f"Parsed event: {title} [{priority.name}]")
            return chronos_event
            
        except Exception as e:
            self.logger.error(f"Failed to parse event: {e}")
            # Return a minimal event object
            return ChronosEvent(
                title=calendar_event.get('summary', 'Parse Error'),
                description=f"Parse error: {str(e)}"
            )
    
    def _parse_datetime(self, dt_data: Optional[Dict[str, Any]]) -> Optional[datetime]:
        """Parse datetime from calendar event data"""
        
        if not dt_data:
            return None
        
        try:
            # Handle dateTime format
            if 'dateTime' in dt_data:
                dt_str = dt_data['dateTime']
                # Remove timezone suffix for parsing
                if dt_str.endswith('Z'):
                    dt_str = dt_str[:-1]
                elif '+' in dt_str:
                    dt_str = dt_str.split('+')[0]
                elif dt_str.count('-') > 2:  # Has timezone
                    dt_str = dt_str.rsplit('-', 1)[0]
                
                return datetime.fromisoformat(dt_str)
            
            # Handle date format (all-day events)
            elif 'date' in dt_data:
                date_str = dt_data['date']
                # For all-day events, create datetime at midnight in local timezone
                # This prevents DST-related day shifts
                local_tz = zoneinfo.ZoneInfo("Europe/Berlin")
                naive_dt = datetime.strptime(date_str, '%Y-%m-%d')
                # Create timezone-aware datetime at midnight local time
                localized_dt = naive_dt.replace(tzinfo=local_tz)
                # Convert to UTC for storage (preserves the date)
                return localized_dt.astimezone(zoneinfo.ZoneInfo("UTC")).replace(tzinfo=None)
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Failed to parse datetime {dt_data}: {e}")
            return None
    
    def _detect_priority(self, title: str, description: str) -> Priority:
        """Detect event priority from title and description"""
        
        content = f"{title} {description}".lower()
        
        # Check for priority keywords
        for priority, keywords in self.priority_keywords.items():
            if any(keyword in content for keyword in keywords):
                return priority
        
        # Default priority
        return Priority.MEDIUM
    
    def _detect_event_type(self, title: str, description: str) -> EventType:
        """Detect event type from title and description"""
        
        content = f"{title} {description}".lower()
        
        # Check for type keywords
        for event_type, keywords in self.type_keywords.items():
            if any(keyword in content for keyword in keywords):
                return event_type
        
        # Default to task
        return EventType.TASK
    
    def _extract_tags(self, description: str) -> List[str]:
        """Extract hashtags from description"""
        
        if not description:
            return []
        
        # Find hashtags
        hashtag_pattern = r'#(\w+)'
        tags = re.findall(hashtag_pattern, description)
        
        return tags

    def _parse_sub_tasks(self, description: str) -> List[SubTask]:
        """Parse checkbox-style sub-tasks from description (v2.2 feature)"""

        if not description:
            return []

        sub_tasks = []

        # Pattern for checkbox-style tasks: [ ] or [x] or [X] followed by text
        checkbox_pattern = r'^\s*\[(.*?)\]\s*(.+)$'

        for line in description.split('\n'):
            line = line.strip()
            match = re.match(checkbox_pattern, line)

            if match:
                checkbox_content = match.group(1).strip()
                task_text = match.group(2).strip()

                if task_text:  # Only create sub-task if there's actual text
                    # Check if checkbox indicates completion (contains x or X)
                    completed = 'x' in checkbox_content.lower()

                    sub_task = SubTask(
                        text=task_text,
                        completed=completed,
                        completed_at=datetime.utcnow() if completed else None
                    )

                    sub_tasks.append(sub_task)

        if sub_tasks:
            self.logger.debug(f"Parsed {len(sub_tasks)} sub-tasks from description")

        return sub_tasks

    def parse_events_batch(self, calendar_events: List[Dict[str, Any]]) -> List[ChronosEvent]:
        """Parse multiple calendar events"""
        
        parsed_events = []
        
        for calendar_event in calendar_events:
            try:
                chronos_event = self.parse_event(calendar_event)
                parsed_events.append(chronos_event)
            except Exception as e:
                self.logger.error(f"Failed to parse event {calendar_event.get('id', 'unknown')}: {e}")
                continue
        
        self.logger.info(f"Parsed {len(parsed_events)} events from {len(calendar_events)} calendar events")
        return parsed_events
    
    def update_event_from_calendar(
        self, 
        chronos_event: ChronosEvent, 
        calendar_event: Dict[str, Any]
    ) -> ChronosEvent:
        """Update existing ChronosEvent with new calendar data"""
        
        # Update basic fields
        chronos_event.title = calendar_event.get('summary', chronos_event.title)
        chronos_event.description = calendar_event.get('description', chronos_event.description)
        chronos_event.location = calendar_event.get('location', chronos_event.location)
        
        # Update datetime
        start_time = self._parse_datetime(calendar_event.get('start'))
        end_time = self._parse_datetime(calendar_event.get('end'))
        
        if start_time:
            chronos_event.start_time = start_time
        if end_time:
            chronos_event.end_time = end_time
        
        # Update estimated duration
        if chronos_event.start_time and chronos_event.end_time:
            chronos_event.estimated_duration = chronos_event.end_time - chronos_event.start_time
        
        # Re-analyze priority and type
        chronos_event.priority = self._detect_priority(chronos_event.title, chronos_event.description)
        chronos_event.event_type = self._detect_event_type(chronos_event.title, chronos_event.description)

        # Refresh tags based on updated description while preserving existing ones
        try:
            existing_tags = list(chronos_event.tags or [])
        except AttributeError:
            existing_tags = []

        new_tags = self._extract_tags(chronos_event.description)
        # Maintain insertion order while avoiding duplicates
        combined_tags = []
        for tag in existing_tags + new_tags:
            if tag and tag not in combined_tags:
                combined_tags.append(tag)
        chronos_event.tags = combined_tags

        # Update sub-tasks (v2.2 feature)
        chronos_event.sub_tasks = self._parse_sub_tasks(chronos_event.description)

        # Update timestamp
        chronos_event.updated_at = datetime.utcnow()
        if hasattr(chronos_event, 'version'):
            chronos_event.version += 1
        
        return chronos_event
