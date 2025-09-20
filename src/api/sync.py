"""
Sync Service for Chronos Engine
Handles calendar synchronization endpoints
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from src.core.calendar_client import GoogleCalendarClient
from src.core.event_parser import EventParser
from src.core.timebox_engine import TimeboxEngine
from src.core.replan_engine import ReplanEngine


# Security
security = HTTPBearer()


class SyncRequest(BaseModel):
    days_ahead: int = 7
    force_refresh: bool = False


class SyncService:
    """Sync service for calendar operations"""
    
    def __init__(
        self,
        calendar_client: GoogleCalendarClient,
        event_parser: EventParser,
        timebox_engine: TimeboxEngine,
        replan_engine: ReplanEngine,
        api_key: str = "development-key-change-in-production"
    ):
        self.calendar_client = calendar_client
        self.event_parser = event_parser
        self.timebox = timebox_engine
        self.replan = replan_engine
        self.api_key = api_key
        
        self.logger = logging.getLogger(__name__)
        self.router = APIRouter()
        self._setup_routes()
    
    def _verify_api_key(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
        """Verify API key"""
        if credentials.credentials != self.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        return True
    
    def _setup_routes(self):
        """Setup sync service routes"""
        
        @self.router.post("/calendar")
        async def sync_calendar(
            request: SyncRequest,
            authenticated: bool = Depends(self._verify_api_key)
        ):
            """Manually trigger calendar synchronization"""
            
            try:
                self.logger.info("Manual calendar sync triggered")
                
                # Authenticate with calendar
                if not await self.calendar_client.authenticate():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Calendar authentication failed"
                    )
                
                # Fetch events
                calendar_events = await self.calendar_client.fetch_events(
                    days_ahead=request.days_ahead
                )
                
                # Parse events
                parsed_events = self.event_parser.parse_events_batch(calendar_events)
                
                sync_result = {
                    "success": True,
                    "sync_time": datetime.utcnow().isoformat(),
                    "events_fetched": len(calendar_events),
                    "events_parsed": len(parsed_events),
                    "days_ahead": request.days_ahead,
                    "events": [event.to_dict() for event in parsed_events]
                }
                
                self.logger.info(f"Calendar sync completed: {len(parsed_events)} events")
                return sync_result
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Calendar sync failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Sync failed: {str(e)}"
                )
        
        @self.router.get("/status")
        async def get_sync_status(
            authenticated: bool = Depends(self._verify_api_key)
        ):
            """Get synchronization status"""
            
            try:
                # Check calendar connection
                auth_status = await self.calendar_client.authenticate()
                
                return {
                    "calendar_connected": auth_status,
                    "last_check": datetime.utcnow().isoformat(),
                    "service_status": "active"
                }
                
            except Exception as e:
                self.logger.error(f"Failed to get sync status: {e}")
                return {
                    "calendar_connected": False,
                    "last_check": datetime.utcnow().isoformat(),
                    "service_status": "error",
                    "error": str(e)
                }
        
        @self.router.post("/analyze")
        async def analyze_schedule(
            target_date: Optional[datetime] = Query(None),
            authenticated: bool = Depends(self._verify_api_key)
        ):
            """Analyze current schedule and provide insights"""
            
            try:
                if not target_date:
                    target_date = datetime.utcnow()
                
                # Fetch current events
                calendar_events = await self.calendar_client.fetch_events(days_ahead=1)
                parsed_events = self.event_parser.parse_events_batch(calendar_events)
                
                # Filter events for target date
                target_events = [
                    e for e in parsed_events
                    if e.start_time and e.start_time.date() == target_date.date()
                ]
                
                # Detect conflicts
                conflicts = await self.replan.detect_conflicts(target_events, target_date)
                
                # Optimize day structure
                day_optimization = await self.timebox.optimize_day_structure(target_events, target_date)
                
                # Suggest focus blocks
                focus_blocks = await self.timebox.suggest_focus_blocks(target_events, target_date)
                
                analysis_result = {
                    "target_date": target_date.date().isoformat(),
                    "total_events": len(target_events),
                    "conflicts_detected": len(conflicts),
                    "conflicts": [
                        {
                            "type": c.type.value,
                            "severity": c.severity,
                            "description": c.description,
                            "suggested_resolution": c.suggested_resolution
                        }
                        for c in conflicts
                    ],
                    "day_optimization": day_optimization,
                    "focus_block_suggestions": [
                        {
                            "suggested_start": fb.suggested_start.isoformat(),
                            "suggested_end": fb.suggested_end.isoformat(),
                            "reason": fb.reason,
                            "confidence": fb.confidence
                        }
                        for fb in focus_blocks
                    ],
                    "analyzed_at": datetime.utcnow().isoformat()
                }
                
                return analysis_result
                
            except Exception as e:
                self.logger.error(f"Schedule analysis failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Analysis failed: {str(e)}"
                )
        
        @self.router.post("/validate")
        async def validate_calendar_connection(
            authenticated: bool = Depends(self._verify_api_key)
        ):
            """Validate calendar connection and permissions"""
            
            try:
                # Test authentication
                auth_success = await self.calendar_client.authenticate()
                
                if not auth_success:
                    return {
                        "valid": False,
                        "error": "Authentication failed",
                        "suggestions": [
                            "Check credentials file",
                            "Verify token file",
                            "Re-run OAuth flow"
                        ]
                    }
                
                # Test basic calendar access
                try:
                    test_events = await self.calendar_client.fetch_events(days_ahead=1, max_results=1)
                    calendar_access = True
                except Exception as e:
                    calendar_access = False
                    calendar_error = str(e)
                
                validation_result = {
                    "valid": auth_success and calendar_access,
                    "authentication": auth_success,
                    "calendar_access": calendar_access,
                    "tested_at": datetime.utcnow().isoformat()
                }
                
                if not calendar_access:
                    validation_result["error"] = calendar_error
                    validation_result["suggestions"] = [
                        "Check calendar permissions",
                        "Verify calendar ID",
                        "Check API quotas"
                    ]
                
                return validation_result
                
            except Exception as e:
                self.logger.error(f"Calendar validation failed: {e}")
                return {
                    "valid": False,
                    "error": str(e),
                    "tested_at": datetime.utcnow().isoformat(),
                    "suggestions": [
                        "Check network connectivity",
                        "Verify service configuration",
                        "Check logs for detailed errors"
                    ]
                }
        
        @self.router.get("/health")
        async def health_check():
            """Health check endpoint (no authentication required)"""
            
            try:
                # Basic health indicators
                health_status = {
                    "status": "healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "chronos-sync",
                    "version": "2.1.0"
                }
                
                # Test calendar client availability
                try:
                    await self.calendar_client.authenticate()
                    health_status["calendar_service"] = "available"
                except Exception:
                    health_status["calendar_service"] = "unavailable"
                    health_status["status"] = "degraded"
                
                return health_status
                
            except Exception as e:
                return {
                    "status": "unhealthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "chronos-sync",
                    "version": "2.1.0",
                    "error": str(e)
                }
