"""
Notification Engine for Chronos - Phase 2 Feature
Multi-channel notification system
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

# Mock HTTP client for development
class MockHttpClient:
    async def post(self, url: str, **kwargs) -> Dict[str, Any]:
        logging.getLogger(__name__).info(f"Mock HTTP POST to {url}")
        return {"status": "success", "message": "Mock notification sent"}


class NotificationType(Enum):
    REMINDER = "reminder"
    CONFLICT = "conflict"
    SUGGESTION = "suggestion"
    UPDATE = "update"
    ERROR = "error"


@dataclass
class Notification:
    """Notification message"""
    id: str
    type: NotificationType
    title: str
    message: str
    event_id: Optional[str] = None
    priority: int = 1  # 1=low, 5=high
    created_at: datetime = None
    scheduled_for: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class NotificationChannel(ABC):
    """Abstract base class for notification channels"""
    
    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """Send notification through this channel"""
        pass
    
    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Get channel name"""
        pass


class WebhookChannel(NotificationChannel):
    """Webhook notification channel"""
    
    def __init__(self, webhook_url: str, api_key: Optional[str] = None):
        self.webhook_url = webhook_url
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)
        self.http_client = MockHttpClient()  # Use mock in development
    
    async def send(self, notification: Notification) -> bool:
        """Send notification via webhook"""
        
        if not self.webhook_url:
            return False
        
        try:
            headers = {'Content-Type': 'application/json'}
            
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            
            payload = {
                'id': notification.id,
                'type': notification.type.value,
                'title': notification.title,
                'message': notification.message,
                'event_id': notification.event_id,
                'priority': notification.priority,
                'timestamp': notification.created_at.isoformat()
            }
            
            response = await self.http_client.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            self.logger.info(f"Webhook notification sent: {notification.title}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send webhook notification: {e}")
            return False
    
    @property
    def channel_name(self) -> str:
        return "webhook"


class EmailChannel(NotificationChannel):
    """Email notification channel (mock implementation)"""
    
    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.logger = logging.getLogger(__name__)
    
    async def send(self, notification: Notification) -> bool:
        """Send notification via email (mock)"""
        
        # Mock implementation - in production this would use real SMTP
        self.logger.info(
            f"Mock email sent: {notification.title} to {self.username}"
        )
        
        # Simulate some processing time
        await asyncio.sleep(0.1)
        
        return True
    
    @property
    def channel_name(self) -> str:
        return "email"


class NotificationEngine:
    """Multi-channel notification engine"""
    
    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self.pending_notifications: List[Notification] = []
        self.sent_notifications: List[Notification] = []
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._task = None
        
        self.logger.info("Notification Engine initialized")
    
    def add_channel(self, channel: NotificationChannel):
        """Add a notification channel"""
        self.channels[channel.channel_name] = channel
        self.logger.info(f"Added notification channel: {channel.channel_name}")
    
    def remove_channel(self, channel_name: str):
        """Remove a notification channel"""
        if channel_name in self.channels:
            del self.channels[channel_name]
            self.logger.info(f"Removed notification channel: {channel_name}")
    
    async def send_notification(
        self, 
        notification: Notification,
        channels: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """Send notification through specified channels"""
        
        if not channels:
            channels = list(self.channels.keys())
        
        results = {}
        
        for channel_name in channels:
            if channel_name in self.channels:
                try:
                    success = await self.channels[channel_name].send(notification)
                    results[channel_name] = success
                    
                    if success:
                        self.logger.debug(f"Notification sent via {channel_name}: {notification.title}")
                    else:
                        self.logger.warning(f"Failed to send notification via {channel_name}")
                        
                except Exception as e:
                    self.logger.error(f"Error sending notification via {channel_name}: {e}")
                    results[channel_name] = False
            else:
                self.logger.warning(f"Channel {channel_name} not found")
                results[channel_name] = False
        
        # Add to sent notifications history
        self.sent_notifications.append(notification)
        
        # Keep only last 1000 notifications
        if len(self.sent_notifications) > 1000:
            self.sent_notifications = self.sent_notifications[-1000:]
        
        return results
    
    async def schedule_notification(
        self, 
        notification: Notification,
        channels: Optional[List[str]] = None
    ):
        """Schedule a notification for future sending"""
        
        notification.scheduled_for = notification.scheduled_for or datetime.utcnow()
        self.pending_notifications.append(notification)
        
        self.logger.debug(
            f"Scheduled notification: {notification.title} for "
            f"{notification.scheduled_for.isoformat()}"
        )
    
    async def send_reminder(
        self, 
        event_id: str,
        event_title: str,
        start_time: datetime,
        reminder_minutes: int = 15
    ):
        """Send event reminder notification"""
        
        notification = Notification(
            id=f"reminder_{event_id}_{datetime.utcnow().timestamp()}",
            type=NotificationType.REMINDER,
            title=f"Reminder: {event_title}",
            message=f"Event '{event_title}' starts in {reminder_minutes} minutes at {start_time.strftime('%H:%M')}",
            event_id=event_id,
            priority=3,
            scheduled_for=start_time - timedelta(minutes=reminder_minutes)
        )
        
        await self.schedule_notification(notification)
    
    async def send_conflict_alert(
        self, 
        event_ids: List[str],
        conflict_description: str
    ):
        """Send scheduling conflict alert"""
        
        notification = Notification(
            id=f"conflict_{datetime.utcnow().timestamp()}",
            type=NotificationType.CONFLICT,
            title="Scheduling Conflict Detected",
            message=conflict_description,
            priority=4
        )
        
        await self.send_notification(notification)
    
    async def send_suggestion(
        self, 
        event_id: str,
        suggestion_title: str,
        suggestion_message: str
    ):
        """Send optimization suggestion"""
        
        notification = Notification(
            id=f"suggestion_{event_id}_{datetime.utcnow().timestamp()}",
            type=NotificationType.SUGGESTION,
            title=suggestion_title,
            message=suggestion_message,
            event_id=event_id,
            priority=2
        )
        
        await self.send_notification(notification)
    
    async def start_scheduler(self):
        """Start the notification scheduler"""
        
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        self.logger.info("Notification scheduler started")
    
    async def stop_scheduler(self):
        """Stop the notification scheduler"""
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Notification scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        
        while self._running:
            try:
                current_time = datetime.utcnow()
                
                # Find due notifications
                due_notifications = [
                    n for n in self.pending_notifications
                    if n.scheduled_for and n.scheduled_for <= current_time
                ]
                
                # Send due notifications
                for notification in due_notifications:
                    await self.send_notification(notification)
                    self.pending_notifications.remove(notification)
                
                # Sleep for 30 seconds before next check
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in notification scheduler: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    def get_notification_history(
        self, 
        limit: int = 100,
        notification_type: Optional[NotificationType] = None
    ) -> List[Dict[str, Any]]:
        """Get notification history"""
        
        notifications = self.sent_notifications
        
        if notification_type:
            notifications = [n for n in notifications if n.type == notification_type]
        
        # Sort by creation time (newest first)
        notifications = sorted(notifications, key=lambda x: x.created_at, reverse=True)
        
        # Limit results
        notifications = notifications[:limit]
        
        return [
            {
                'id': n.id,
                'type': n.type.value,
                'title': n.title,
                'message': n.message,
                'event_id': n.event_id,
                'priority': n.priority,
                'created_at': n.created_at.isoformat(),
                'scheduled_for': n.scheduled_for.isoformat() if n.scheduled_for else None
            }
            for n in notifications
        ]
    
    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Get pending scheduled notifications"""
        
        return [
            {
                'id': n.id,
                'type': n.type.value,
                'title': n.title,
                'message': n.message,
                'event_id': n.event_id,
                'priority': n.priority,
                'created_at': n.created_at.isoformat(),
                'scheduled_for': n.scheduled_for.isoformat() if n.scheduled_for else None
            }
            for n in self.pending_notifications
        ]
