"""
UNDEFINED Guard Plugin for Chronos Engine v2.2
Handles malformed command-like titles by marking them as UNDEFINED

Security-first implementation that prevents infinite loops and only processes
user-created events, not system events.
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

from src.core.models import ChronosEvent, EventStatus
from src.core.plugin_manager import EventPlugin


class UndefinedGuardPlugin(EventPlugin):
    """
    UNDEFINED Guard Plugin - Malformed command detection

    Detects titles that look like commands but don't match exact patterns:
    - Near-matches to NOTIZ:, URL:, ACTION: (case variations, typos)
    - Marks them as UNDEFINED: to prevent confusion
    - Only processes user events, never system/scheduled events
    - Includes loop prevention
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.enabled = True
        self.command_patterns = [
            # Lowercase versions of proper commands (malformed)
            r'^notiz\s*:',     # notiz: (should be NOTIZ:)
            r'^url\s*:',       # url: (should be URL:)
            r'^action\s*:',    # action: (should be ACTION:)

            # Common typos and alternatives
            r'^note\s*:',      # common typo: note instead of notiz
            r'^akti[oa]n\s*:', # common typos: aktion, aktian
            r'^link\s*:',      # alternative for url
            r'^cmd\s*:',       # cmd: abbreviation
            r'^command\s*:',   # command: full word
        ]

        # Proper commands that should NOT be marked (excluded patterns)
        self.proper_commands = [
            r'^NOTIZ\s*:',
            r'^URL\s*:',
            r'^ACTION\s*:',
        ]

    @property
    def name(self) -> str:
        return "undefined_guard"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Guards against malformed commands by marking them as UNDEFINED"

    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize plugin with configuration"""
        try:
            self.logger.info("[UNDEFINED_GUARD] Initializing UNDEFINED Guard Plugin")
            self.context = context

            # Load configuration
            config = context.get('config', {})
            guard_config = config.get('undefined_guard', {})
            self.enabled = guard_config.get('enabled', True)

            # Additional patterns from config
            extra_patterns = guard_config.get('extra_patterns', [])
            self.command_patterns.extend(extra_patterns)

            self.logger.info(f"[UNDEFINED_GUARD] Monitoring {len(self.command_patterns)} command patterns")
            self.logger.info(f"[UNDEFINED_GUARD] Plugin enabled: {self.enabled}")

            return True

        except Exception as e:
            self.logger.error(f"[UNDEFINED_GUARD] Initialization failed: {e}")
            return False

    async def cleanup(self):
        """Cleanup plugin resources"""
        self.logger.info("[UNDEFINED_GUARD] UNDEFINED Guard Plugin cleaned up")

    async def process_event(self, event: ChronosEvent) -> Optional[ChronosEvent]:
        """
        Process event for malformed command patterns

        Returns:
        - ChronosEvent: Event with UNDEFINED: prefix if malformed command detected
        - ChronosEvent: Original event if no issues detected
        """

        if not self.enabled:
            return event

        try:
            # Security: Only process user events, never system events
            if self._is_system_event(event):
                return event

            # Loop prevention: Skip already marked UNDEFINED events but restore original title
            if event.title.startswith("UNDEFINED:"):
                cleaned_title = event.title[len("UNDEFINED:"):].strip()
                if cleaned_title:
                    event.title = cleaned_title
                return event

            # Check for malformed command patterns
            title = event.title.strip()
            if not title:
                return event

            # First check if it's a proper command (should not be marked)
            for proper_pattern in self.proper_commands:
                if re.match(proper_pattern, title):
                    return event  # It's a proper command, don't mark

            # Pattern matching for malformed commands (case sensitive now)
            for pattern in self.command_patterns:
                if re.match(pattern, title):
                    # Found a malformed command
                    self.logger.warning(f"[UNDEFINED_GUARD] Malformed command detected: {title[:50]}...")

                    # Mark as UNDEFINED
                    event.title = f"UNDEFINED: {title}"
                    event.description = f"[GUARD] Original title appeared to be a malformed command. " \
                                      f"Original: {title}\n\n{event.description or ''}"

                    self.logger.info(f"[UNDEFINED_GUARD] Marked event as UNDEFINED: {event.id}")
                    return event

            # No malformed commands detected
            return event

        except Exception as e:
            self.logger.error(f"[UNDEFINED_GUARD] Error processing event {event.id}: {e}")
            # On error, return original event for safety
            return event

    def _is_system_event(self, event: ChronosEvent) -> bool:
        """
        Check if this is a system-generated event that should not be processed

        Security: Never modify stable/system events
        """
        try:
            # Check event origin/source
            if hasattr(event, 'origin') and event.origin == 'system':
                return True

            # Check event status - don't modify in-progress events (but SCHEDULED is ok for user events)
            if event.status == EventStatus.IN_PROGRESS:
                return True

            # Check if event has calendar_id indicating sync source
            if event.calendar_id and event.calendar_id != 'local':
                return True

            # Check creation metadata (if available)
            if hasattr(event, 'created_by') and event.created_by == 'system':
                return True

            return False

        except Exception as e:
            self.logger.error(f"[UNDEFINED_GUARD] Error checking system event: {e}")
            # On error, assume it's a system event for safety
            return True


# Plugin registration
def get_plugins():
    """Return plugin instances for auto-loading"""
    return [UndefinedGuardPlugin()]