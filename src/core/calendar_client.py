"""
Google Calendar client for Chronos Engine v2.1 - REAL OAuth2 Implementation
Replaces mock implementation with production-ready Google Calendar API
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

# Real Google Calendar API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the token file.
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events'
]


class GoogleCalendarClient:
    """Production Google Calendar API client with OAuth2 authentication"""
    
    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self.logger = logging.getLogger(__name__)
        self.service = None
        self.credentials = None
        
        # Authentication mode detection
        self.auth_mode = self._detect_auth_mode()
        
        self.logger.info(f"Google Calendar Client initialized - Auth mode: {self.auth_mode}")
    
    def _detect_auth_mode(self) -> str:
        """Detect authentication mode based on credentials file"""
        if not self.credentials_file.exists():
            return "mock"  # Fall back to mock if no credentials
        
        try:
            with open(self.credentials_file, 'r') as f:
                creds_data = json.load(f)
                if creds_data.get('type') == 'service_account':
                    return "service_account"
                elif creds_data.get('installed') or creds_data.get('web'):
                    return "oauth2"
                else:
                    return "mock"
        except Exception:
            return "mock"
    
    async def authenticate(self) -> bool:
        """Authenticate with Google Calendar API"""
        try:
            if self.auth_mode == "service_account":
                return await self._authenticate_service_account()
            elif self.auth_mode == "oauth2":
                return await self._authenticate_oauth2()
            else:
                return await self._authenticate_mock()
                
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False
    
    async def _authenticate_service_account(self) -> bool:
        """Authenticate using service account credentials"""
        try:
            self.logger.info("🔐 Authenticating with service account...")
            
            self.credentials = service_account.Credentials.from_service_account_file(
                str(self.credentials_file),
                scopes=SCOPES
            )
            
            # Build the service
            self.service = build('calendar', 'v3', credentials=self.credentials)
            
            # Test the connection
            await self._test_connection()
            
            self.logger.info("✅ Service account authentication successful")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Service account authentication failed: {e}")
            return False
    
    async def _authenticate_oauth2(self) -> bool:
        """Authenticate using OAuth2 flow"""
        try:
            self.logger.info("🔐 Starting OAuth2 authentication...")
            
            creds = None
            
            # Check if token file exists and load existing credentials
            if self.token_file.exists():
                try:
                    self.credentials = Credentials.from_authorized_user_file(
                        str(self.token_file), SCOPES
                    )
                    creds = self.credentials
                except Exception as e:
                    self.logger.warning(f"Could not load existing token: {e}")
            
            # If there are no valid credentials, run OAuth2 flow
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    # Refresh expired credentials
                    self.logger.info("🔄 Refreshing expired credentials...")
                    creds.refresh(Request())
                else:
                    # Run new OAuth2 flow
                    self.logger.info("🌐 Starting OAuth2 authorization flow...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_file), SCOPES
                    )
                    
                    # Run local server for OAuth2 callback
                    creds = flow.run_local_server(
                        port=8080,
                        access_type='offline',
                        prompt='consent'
                    )
                
                # Save credentials for next run
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                
                self.logger.info("💾 OAuth2 credentials saved")
            
            self.credentials = creds
            self.service = build('calendar', 'v3', credentials=self.credentials)
            
            # Test the connection
            await self._test_connection()
            
            self.logger.info("✅ OAuth2 authentication successful")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ OAuth2 authentication failed: {e}")
            return False
    
    async def _authenticate_mock(self) -> bool:
        """Fallback to mock authentication for development"""
        from src.core.mock_calendar import MockCalendarService, MockCredentials
        
        self.logger.info("🔧 Using mock authentication (no credentials found)")
        
        mock_creds_data = {
            'client_id': 'mock_client_id',
            'client_secret': 'mock_client_secret',
            'refresh_token': 'mock_refresh_token',
            'type': 'authorized_user'
        }
        
        self.credentials = MockCredentials(mock_creds_data)
        self.service = MockCalendarService(self.credentials)
        
        self.logger.info("✅ Mock authentication ready")
        return True
    
    async def _test_connection(self):
        """Test Google Calendar API connection"""
        try:
            # Try to list calendars to test connection
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            self.logger.info(f"📅 Connected to {len(calendars)} calendar(s)")
            
            for calendar in calendars[:3]:  # Log first 3 calendars
                self.logger.debug(f"  - {calendar.get('summary', 'Unknown')}")
                
        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error("❌ Access denied - check API permissions and quotas")
            else:
                self.logger.error(f"❌ API test failed: {e}")
            raise
    
    async def fetch_events(
        self, 
        calendar_id: str = 'primary',
        days_ahead: int = 7,
        max_results: int = 250
    ) -> List[Dict[str, Any]]:
        """Fetch events from Google Calendar"""
        
        if not self.service:
            if not await self.authenticate():
                raise Exception("Authentication required")
        
        try:
            time_min = datetime.utcnow()
            time_max = time_min + timedelta(days=days_ahead)
            
            self.logger.debug(f"📅 Fetching events from {time_min.date()} to {time_max.date()}")
            
            # Fetch events from Google Calendar API
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat() + 'Z',
                timeMax=time_max.isoformat() + 'Z',
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime',
                fields='items(id,summary,description,start,end,attendees,location,status,created,updated)'
            ).execute()
            
            events = events_result.get('items', [])
            
            self.logger.info(f"📊 Fetched {len(events)} events from Google Calendar")
            return events
            
        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error("❌ Calendar access denied - check permissions")
            elif e.resp.status == 404:
                self.logger.error(f"❌ Calendar '{calendar_id}' not found")
            else:
                self.logger.error(f"❌ Failed to fetch events: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error fetching events: {e}")
            raise
    
    async def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new calendar event"""
        
        if not self.service:
            if not await self.authenticate():
                raise Exception("Authentication required")
        
        try:
            # Format event data for Google Calendar API
            formatted_event = self._format_event_for_api(event_data)
            
            self.logger.debug(f"📝 Creating event: {formatted_event.get('summary')}")
            
            # Create event via API
            event = self.service.events().insert(
                calendarId='primary',
                body=formatted_event
            ).execute()
            
            self.logger.info(f"✅ Created event: {event.get('summary')} (ID: {event.get('id')})")
            return event
            
        except HttpError as e:
            self.logger.error(f"❌ Failed to create event: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error creating event: {e}")
            raise
    
    async def update_event(
        self, 
        event_id: str, 
        event_data: Dict[str, Any],
        calendar_id: str = 'primary'
    ) -> Dict[str, Any]:
        """Update an existing calendar event"""
        
        if not self.service:
            if not await self.authenticate():
                raise Exception("Authentication required")
        
        try:
            # Get existing event first
            existing_event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Merge updates with existing event
            updated_event = {**existing_event, **self._format_event_for_api(event_data)}
            
            self.logger.debug(f"📝 Updating event: {event_id}")
            
            # Update via API
            event = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=updated_event
            ).execute()
            
            self.logger.info(f"✅ Updated event: {event.get('summary')} (ID: {event_id})")
            return event
            
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.error(f"❌ Event '{event_id}' not found")
            else:
                self.logger.error(f"❌ Failed to update event: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error updating event: {e}")
            raise
    
    async def delete_event(
        self, 
        event_id: str, 
        calendar_id: str = 'primary'
    ) -> bool:
        """Delete a calendar event"""
        
        if not self.service:
            if not await self.authenticate():
                raise Exception("Authentication required")
        
        try:
            self.logger.debug(f"🗑️ Deleting event: {event_id}")
            
            # Delete via API
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            self.logger.info(f"✅ Deleted event: {event_id}")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"⚠️ Event '{event_id}' not found (already deleted?)")
                return True  # Consider as success if already gone
            elif e.resp.status == 410:
                self.logger.warning(f"⚠️ Event '{event_id}' was already deleted")
                return True
            else:
                self.logger.error(f"❌ Failed to delete event: {e}")
                raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error deleting event: {e}")
            raise
    
    def _format_event_for_api(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format event data for Google Calendar API"""
        
        formatted = {}
        
        # Basic fields
        if 'title' in event_data:
            formatted['summary'] = event_data['title']
        if 'description' in event_data:
            formatted['description'] = event_data['description']
        if 'location' in event_data:
            formatted['location'] = event_data['location']
        
        # Time fields
        if 'start_time' in event_data:
            if isinstance(event_data['start_time'], datetime):
                formatted['start'] = {
                    'dateTime': event_data['start_time'].isoformat(),
                    'timeZone': 'UTC'
                }
            else:
                formatted['start'] = event_data['start_time']
        
        if 'end_time' in event_data:
            if isinstance(event_data['end_time'], datetime):
                formatted['end'] = {
                    'dateTime': event_data['end_time'].isoformat(),
                    'timeZone': 'UTC'
                }
            else:
                formatted['end'] = event_data['end_time']
        
        # Attendees
        if 'attendees' in event_data and event_data['attendees']:
            formatted['attendees'] = [
                {'email': email} for email in event_data['attendees']
                if isinstance(email, str) and '@' in email
            ]
        
        return formatted
    
    async def get_calendar_list(self) -> List[Dict[str, Any]]:
        """Get list of available calendars"""
        
        if not self.service:
            if not await self.authenticate():
                raise Exception("Authentication required")
        
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            self.logger.info(f"📅 Found {len(calendars)} calendar(s)")
            return calendars
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get calendar list: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for Google Calendar connection"""
        
        try:
            if not self.service:
                auth_success = await self.authenticate()
                if not auth_success:
                    return {
                        'status': 'unhealthy',
                        'error': 'Authentication failed',
                        'auth_mode': self.auth_mode
                    }
            
            # Quick API test
            await self._test_connection()
            
            return {
                'status': 'healthy',
                'auth_mode': self.auth_mode,
                'credentials_file_exists': self.credentials_file.exists(),
                'token_file_exists': self.token_file.exists()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'auth_mode': self.auth_mode
            }
