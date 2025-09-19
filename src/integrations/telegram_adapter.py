"""
Telegram integration adapter for Chronos Engine
Handles incoming webhook messages and outgoing notifications
"""

import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
import httpx

from src.core.outbox import OutboxService, outbox_registry
from src.core.security import security_service
from src.core.schema_extensions import IntegrationConfigDB


@dataclass
class TelegramMessage:
    """Telegram message model"""
    message_id: int
    chat_id: int
    user_id: int
    text: str
    date: datetime
    chat_type: str = "private"
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @classmethod
    def from_telegram_update(cls, update: Dict[str, Any]) -> 'TelegramMessage':
        """Create from Telegram webhook update"""
        message = update.get('message', {})
        from_user = message.get('from', {})
        chat = message.get('chat', {})

        return cls(
            message_id=message.get('message_id', 0),
            chat_id=chat.get('id', 0),
            user_id=from_user.get('id', 0),
            text=message.get('text', ''),
            date=datetime.fromtimestamp(message.get('date', 0)),
            chat_type=chat.get('type', 'private'),
            username=from_user.get('username'),
            first_name=from_user.get('first_name'),
            last_name=from_user.get('last_name')
        )


@dataclass
class TelegramConfig:
    """Telegram integration configuration"""
    bot_token: str
    webhook_secret: Optional[str] = None
    allowed_chat_ids: List[int] = field(default_factory=list)
    allowed_users: List[int] = field(default_factory=list)
    enable_commands: bool = True
    enable_notifications: bool = True
    api_base_url: str = "https://api.telegram.org"


class TelegramAdapter:
    """Telegram integration adapter"""

    def __init__(self, config: TelegramConfig, outbox_service: OutboxService,
                 db_session_factory=None):
        self.config = config
        self.outbox_service = outbox_service
        self.db_session_factory = db_session_factory

        # Register outbox handler
        outbox_registry.register_handler('TELEGRAM', self._handle_outbox_entry)

    async def handle_webhook(self, request: Request, update: Dict[str, Any]) -> Dict[str, str]:
        """Handle incoming Telegram webhook"""
        # Verify webhook signature if configured
        if self.config.webhook_secret:
            if not await self._verify_webhook_signature(request):
                raise HTTPException(401, "Invalid webhook signature")

        # Parse message
        if 'message' not in update:
            return {"status": "ignored", "reason": "No message in update"}

        message = TelegramMessage.from_telegram_update(update)

        # Check authorization
        if not self._is_authorized(message):
            await self._send_unauthorized_response(message)
            return {"status": "unauthorized"}

        # Process message
        result = await self._process_message(message)

        return {"status": "processed", "action": result.get("action", "none")}

    async def _verify_webhook_signature(self, request: Request) -> bool:
        """Verify Telegram webhook signature"""
        # Telegram uses X-Telegram-Bot-Api-Secret-Token header
        received_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if not received_token:
            return False

        return hmac.compare_digest(received_token, self.config.webhook_secret)

    def _is_authorized(self, message: TelegramMessage) -> bool:
        """Check if user/chat is authorized"""
        # Check allowed chat IDs
        if self.config.allowed_chat_ids:
            if message.chat_id not in self.config.allowed_chat_ids:
                return False

        # Check allowed users
        if self.config.allowed_users:
            if message.user_id not in self.config.allowed_users:
                return False

        return True

    async def _send_unauthorized_response(self, message: TelegramMessage):
        """Send unauthorized response"""
        response_text = "⚠️ You are not authorized to use this bot."
        await self._send_message(message.chat_id, response_text)

    async def _process_message(self, message: TelegramMessage) -> Dict[str, Any]:
        """Process incoming message and generate appropriate response"""
        text = message.text.strip()

        # Handle commands
        if text.startswith('/'):
            return await self._handle_command(message)

        # Handle natural language input
        if self.config.enable_commands:
            return await self._handle_natural_input(message)

        return {"action": "ignored"}

    async def _handle_command(self, message: TelegramMessage) -> Dict[str, Any]:
        """Handle bot commands"""
        text = message.text.strip()
        parts = text.split(' ', 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == '/start':
            welcome_text = """
🤖 Welcome to Chronos Engine Bot!

Available commands:
/help - Show this help message
/status - Show system status
/events - List upcoming events
/create - Create a new event

You can also send natural text like:
"Create meeting tomorrow at 2pm"
"NOTIZ: Important reminder"
"ACTION: Send email to team"
            """.strip()
            await self._send_message(message.chat_id, welcome_text)
            return {"action": "welcome_sent"}

        elif command == '/help':
            help_text = """
🤖 Chronos Engine Bot Commands:

📅 Event Management:
/events - List upcoming events
/create [title] - Create new event
/status - System status

💬 Natural Language:
You can also use natural language:
• "Meeting tomorrow 2pm with John"
• "NOTIZ: Don't forget to call client"
• "ACTION: Send reminder email"
• "URL: https://example.com Important link"

⚙️ The bot supports the same command syntax as the main system.
            """.strip()
            await self._send_message(message.chat_id, help_text)
            return {"action": "help_sent"}

        elif command == '/status':
            status_text = await self._get_system_status()
            await self._send_message(message.chat_id, status_text)
            return {"action": "status_sent"}

        elif command == '/events':
            events_text = await self._get_upcoming_events()
            await self._send_message(message.chat_id, events_text)
            return {"action": "events_sent"}

        else:
            error_text = f"❌ Unknown command: {command}\nUse /help for available commands."
            await self._send_message(message.chat_id, error_text)
            return {"action": "error_sent"}

    async def _handle_natural_input(self, message: TelegramMessage) -> Dict[str, Any]:
        """Handle natural language input"""
        text = message.text.strip()

        # Check for special command patterns
        if text.startswith('NOTIZ:'):
            return await self._handle_note_command(message, text)
        elif text.startswith('ACTION:'):
            return await self._handle_action_command(message, text)
        elif text.startswith('URL:'):
            return await self._handle_url_command(message, text)
        else:
            # Try to parse as event creation
            return await self._handle_event_creation(message, text)

    async def _handle_note_command(self, message: TelegramMessage, text: str) -> Dict[str, Any]:
        """Handle NOTIZ: commands"""
        note_content = text[6:].strip()  # Remove "NOTIZ:" prefix

        if not note_content:
            await self._send_message(message.chat_id, "❌ Note content cannot be empty.")
            return {"action": "error"}

        # Store note in database
        note_data = {
            "content": note_content,
            "source": "telegram",
            "user_id": message.user_id,
            "chat_id": message.chat_id,
            "created_at": datetime.now().isoformat()
        }

        # Add to outbox for processing
        await self.outbox_service.add_entry(
            target_system="CHRONOS",
            event_type="note_created",
            payload=note_data,
            idempotency_key=f"telegram_note_{message.message_id}"
        )

        await self._send_message(message.chat_id, f"📝 Note saved: {note_content}")
        return {"action": "note_created"}

    async def _handle_action_command(self, message: TelegramMessage, text: str) -> Dict[str, Any]:
        """Handle ACTION: commands"""
        action_content = text[7:].strip()  # Remove "ACTION:" prefix

        if not action_content:
            await self._send_message(message.chat_id, "❌ Action content cannot be empty.")
            return {"action": "error"}

        # Parse action (simple format: SYSTEM command params)
        parts = action_content.split(' ', 2)
        if len(parts) < 2:
            await self._send_message(message.chat_id, "❌ Invalid action format. Use: ACTION: SYSTEM command [params]")
            return {"action": "error"}

        target_system = parts[0].upper()
        command = parts[1]
        params = parts[2] if len(parts) > 2 else ""

        # Create action data
        action_data = {
            "target_system": target_system,
            "command": command,
            "parameters": {"message": params} if params else {},
            "source": "telegram",
            "user_id": message.user_id,
            "chat_id": message.chat_id,
            "created_at": datetime.now().isoformat()
        }

        # Add to outbox for processing
        await self.outbox_service.add_entry(
            target_system=target_system,
            event_type="action_requested",
            payload=action_data,
            idempotency_key=f"telegram_action_{message.message_id}"
        )

        await self._send_message(message.chat_id, f"⚡ Action queued: {target_system} {command}")
        return {"action": "action_created"}

    async def _handle_url_command(self, message: TelegramMessage, text: str) -> Dict[str, Any]:
        """Handle URL: commands"""
        url_content = text[4:].strip()  # Remove "URL:" prefix
        parts = url_content.split(' ', 1)

        if not parts[0]:
            await self._send_message(message.chat_id, "❌ URL cannot be empty.")
            return {"action": "error"}

        url = parts[0]
        description = parts[1] if len(parts) > 1 else ""

        # Store URL payload
        url_data = {
            "url": url,
            "description": description,
            "source": "telegram",
            "user_id": message.user_id,
            "chat_id": message.chat_id,
            "created_at": datetime.now().isoformat()
        }

        # Add to outbox for processing
        await self.outbox_service.add_entry(
            target_system="CHRONOS",
            event_type="url_saved",
            payload=url_data,
            idempotency_key=f"telegram_url_{message.message_id}"
        )

        await self._send_message(message.chat_id, f"🔗 URL saved: {url}")
        return {"action": "url_saved"}

    async def _handle_event_creation(self, message: TelegramMessage, text: str) -> Dict[str, Any]:
        """Handle event creation from natural language"""
        # Simple event creation - could be enhanced with NLP
        event_data = {
            "title": text,
            "description": f"Created via Telegram by @{message.username or message.first_name}",
            "source": "telegram",
            "user_id": message.user_id,
            "chat_id": message.chat_id,
            "created_at": datetime.now().isoformat()
        }

        # Add to outbox for processing
        await self.outbox_service.add_entry(
            target_system="CHRONOS",
            event_type="event_create_request",
            payload=event_data,
            idempotency_key=f"telegram_event_{message.message_id}"
        )

        await self._send_message(message.chat_id, f"📅 Event creation requested: {text}")
        return {"action": "event_requested"}

    async def _get_system_status(self) -> str:
        """Get system status text"""
        try:
            # This would call the health endpoint
            return "🟢 Chronos Engine is running normally"
        except Exception:
            return "🔴 Chronos Engine status unknown"

    async def _get_upcoming_events(self) -> str:
        """Get upcoming events text"""
        try:
            # This would query the database for upcoming events
            return "📅 No upcoming events found"
        except Exception:
            return "❌ Error retrieving events"

    async def _send_message(self, chat_id: int, text: str,
                          parse_mode: str = "Markdown") -> bool:
        """Send message to Telegram"""
        try:
            url = f"{self.config.api_base_url}/bot{self.config.bot_token}/sendMessage"

            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, timeout=10.0)
                return response.status_code == 200

        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False

    async def _handle_outbox_entry(self, entry) -> bool:
        """Handle outbound messages via outbox"""
        try:
            payload = entry.payload

            if entry.event_type == "notification":
                # Send notification message
                chat_id = payload.get("chat_id")
                message = payload.get("message", "")
                title = payload.get("title", "")

                if title:
                    text = f"🔔 *{title}*\n\n{message}"
                else:
                    text = message

                return await self._send_message(chat_id, text)

            elif entry.event_type == "action_status":
                # Send action status update
                chat_id = payload.get("chat_id")
                action = payload.get("action", "")
                status = payload.get("status", "")

                status_emoji = {
                    "completed": "✅",
                    "failed": "❌",
                    "processing": "⏳"
                }.get(status, "ℹ️")

                text = f"{status_emoji} Action {status}: {action}"
                return await self._send_message(chat_id, text)

            return True

        except Exception as e:
            print(f"Telegram outbox handler error: {e}")
            return False


async def create_telegram_adapter(db_session_factory=None,
                                outbox_service=None) -> Optional[TelegramAdapter]:
    """Create Telegram adapter from database configuration"""
    if not db_session_factory:
        return None

    try:
        from sqlalchemy import select

        async with db_session_factory() as session:
            result = await session.execute(
                select(IntegrationConfigDB).where(
                    IntegrationConfigDB.system_name == "TELEGRAM",
                    IntegrationConfigDB.enabled == True
                )
            )
            config_db = result.scalar_one_or_none()

            if not config_db:
                return None

            config_data = config_db.config_data
            telegram_config = TelegramConfig(
                bot_token=config_data.get("bot_token", ""),
                webhook_secret=config_data.get("webhook_secret"),
                allowed_chat_ids=config_data.get("allowed_chat_ids", []),
                allowed_users=config_data.get("allowed_users", []),
                enable_commands=config_data.get("enable_commands", True),
                enable_notifications=config_data.get("enable_notifications", True)
            )

            if not telegram_config.bot_token:
                return None

            return TelegramAdapter(telegram_config, outbox_service, db_session_factory)

    except Exception as e:
        print(f"Failed to create Telegram adapter: {e}")
        return None