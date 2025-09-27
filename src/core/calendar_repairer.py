"""
Calendar Repairer Plugin - Repairs keyword-prefixed events in calendar backends
Pipeline: UndefinedGuard → CalendarRepairer → KeywordEnricher → command_handler

This plugin:
1. Parses keyword-prefixed events (BDAY:, RIP:, etc.)
2. Formats them into nice titles
3. Writes back to calendar backend (CalDAV/Google)
4. Sets idempotency markers (X-CHRONOS-* or extendedProperties)
5. Prepares enrichment data for later plugins
"""

import re
import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict

from src.core.models import ChronosEvent


@dataclass
class ParsedPayload:
    """Parsed event payload from keyword processing"""
    name: str
    label: Optional[str] = None
    date: Optional[datetime] = None
    date_iso: Optional[str] = None
    locale: str = "en"
    original_text: str = ""
    needs_review: bool = False


@dataclass
class RepairRule:
    """Configuration rule for keyword repair"""
    id: str
    keywords: List[str]
    title_template: str
    all_day: bool = True
    rrule: str = "FREQ=YEARLY"
    leap_day_policy: str = "FEB_28"
    age_suffix_template: Optional[str] = None
    years_since_suffix_template: Optional[str] = None
    label_from_payload: bool = False
    warn_offset_days: Optional[int] = None
    link_to_rule: Optional[str] = None
    enrich: Dict[str, Any] = None


@dataclass
class RepairResult:
    """Result of repair operation"""
    success: bool
    patched: bool = False
    skipped: bool = False
    needs_review: bool = False
    readonly: bool = False
    error: Optional[str] = None
    rule_id: Optional[str] = None
    new_title: Optional[str] = None
    enrichment_data: Dict[str, Any] = None
    etag_before: Optional[str] = None
    etag_after: Optional[str] = None
    elapsed_ms: float = 0.0


class CalendarRepairer:
    """
    Calendar Repairer Plugin

    Processes keyword-prefixed events and repairs them in calendar backends
    (CalDAV/Radicale or Google Calendar) before any other processing takes place.
    """

    def __init__(self, config: Dict[str, Any], source_manager=None):
        # Store full config for later reference
        self.config = config

        # Extract nested config from calendar_repairer section (fallback to repair_and_enrich for backward compatibility)
        repair_config = config.get('calendar_repairer', config.get('repair_and_enrich', {}))
        self.parsing_config = repair_config.get('parsing', config.get('parsing', {}))
        self.rules_config = repair_config.get('rules', config.get('rules', []))
        self.idempotency_config = repair_config.get('idempotency', {})
        self.series_policy_config = repair_config.get('series_policy', {})

        # Store source manager for backend-agnostic operations
        self.source_manager = source_manager
        self.logger = logging.getLogger(__name__)

        # Build rules lookup
        self.rules = self._build_rules()
        self.keyword_to_rule = self._build_keyword_lookup()

        # Configuration
        self.enabled = repair_config.get('enabled', True)
        self.reserved_prefixes = set(
            prefix.upper() for prefix in repair_config.get('reserved_prefixes', ['ACTION', 'MEETING', 'CALL'])
        )
        self.readonly_fallback = repair_config.get('readonly_fallback', 'internal_enrich_only')

        # Parsing settings
        self.day_first = self.parsing_config.get('day_first', True)
        self.year_optional = self.parsing_config.get('year_optional', True)
        self.strict_when_ambiguous = self.parsing_config.get('strict_when_ambiguous', True)
        self.accept_separators = self.parsing_config.get('accept_date_separators', ['.', '-', '/'])

        # Idempotency settings
        self.idempotency_config = self.config.get('idempotency', {})
        self.marker_key = self.idempotency_config.get('marker_key', 'chronos.cleaned')
        self.marker_value = self.idempotency_config.get('marker_value', 'v1')

        # Google Calendar settings
        self.google_config = self.config.get('google_patch', {})
        self.send_updates = self.google_config.get('send_updates', 'none')
        self.use_if_match = self.google_config.get('use_if_match', True)

        # Metrics
        self.metrics = {
            'repair_attempt_total': {},
            'repair_success_total': {},
            'repair_conflict_total': {},
            'readonly_skip_total': 0,
            'enrich_applied_total': {}
        }

    def _build_rules(self) -> Dict[str, RepairRule]:
        """Build repair rules from configuration"""
        rules = {}
        for rule_config in self.rules_config:
            rule = RepairRule(
                id=rule_config['id'],
                keywords=[kw.upper() for kw in rule_config['keywords']],
                title_template=rule_config['title_template'],
                all_day=rule_config.get('all_day', True),
                rrule=rule_config.get('rrule', 'FREQ=YEARLY'),
                leap_day_policy=rule_config.get('leap_day_policy', 'FEB_28'),
                age_suffix_template=rule_config.get('age_suffix_template'),
                years_since_suffix_template=rule_config.get('years_since_suffix_template'),
                label_from_payload=rule_config.get('label_from_payload', False),
                warn_offset_days=rule_config.get('warn_offset_days'),
                link_to_rule=rule_config.get('link_to_rule'),
                enrich=rule_config.get('enrich', {})
            )
            rules[rule.id] = rule
        return rules

    def _build_keyword_lookup(self) -> Dict[str, str]:
        """Build keyword to rule ID lookup"""
        lookup = {}
        for rule_id, rule in self.rules.items():
            for keyword in rule.keywords:
                lookup[keyword] = rule_id
        return lookup

    def is_keyword_event(self, event_title: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if event title starts with a recognized keyword

        Returns:
            (is_keyword_event, keyword, rule_id)
        """
        if not event_title or ':' not in event_title:
            return False, None, None

        # Extract potential keyword before first colon
        parts = event_title.split(':', 1)
        if len(parts) != 2:
            return False, None, None

        potential_keyword = parts[0].strip().upper()

        # Check if it's a reserved prefix (never rewritten)
        if potential_keyword in self.reserved_prefixes:
            return False, None, None

        # Check if it matches a repair rule
        rule_id = self.keyword_to_rule.get(potential_keyword)
        if rule_id:
            return True, potential_keyword, rule_id

        return False, None, None

    def parse_payload(self, payload: str, original_text: str = "") -> ParsedPayload:
        """
        Parse the payload text after the keyword

        Format: <name/label> [date]
        Date formats: dd.mm.yyyy | dd.mm. | dd-mm-yyyy | dd/mm/yyyy
        """
        payload = payload.strip()
        if not payload:
            return ParsedPayload(name="", original_text=original_text, needs_review=True)

        # Date pattern - supports various separators and optional year
        separators = '|'.join(re.escape(sep) for sep in self.accept_separators)
        date_pattern = rf'\b(\d{{1,2}})({separators})(\d{{1,2}})(?:({separators})(\d{{4}}))?\b'

        # Find all potential dates
        date_matches = list(re.finditer(date_pattern, payload))

        if not date_matches:
            # No date found, everything is the name
            return ParsedPayload(
                name=payload.strip(),
                original_text=original_text
            )

        # Use the last (rightmost) date match
        date_match = date_matches[-1]

        # Extract name (everything before the date)
        name_part = payload[:date_match.start()].strip()
        if not name_part:
            name_part = "Unknown"

        # Parse the date
        day_str = date_match.group(1)
        separator1 = date_match.group(2)
        month_str = date_match.group(3)
        separator2 = date_match.group(4)
        year_str = date_match.group(5)

        try:
            day = int(day_str)
            month = int(month_str)

            # Handle ambiguous dates (e.g., 03/07 could be March 7 or July 3)
            if self.day_first:
                parsed_day, parsed_month = day, month
            else:
                parsed_day, parsed_month = month, day

            # Check for ambiguity and strict mode
            is_ambiguous = (day <= 12 and month <= 12 and day != month)
            if is_ambiguous and self.strict_when_ambiguous:
                return ParsedPayload(
                    name=name_part,
                    original_text=original_text,
                    needs_review=True
                )

            # Validate day/month ranges
            if not (1 <= parsed_day <= 31 and 1 <= parsed_month <= 12):
                return ParsedPayload(
                    name=name_part,
                    original_text=original_text,
                    needs_review=True
                )

            # Handle year
            current_year = datetime.now().year
            if year_str:
                parsed_year = int(year_str)
            else:
                # If no year provided, use current year
                parsed_year = current_year

            # Create date object
            try:
                parsed_date = datetime(parsed_year, parsed_month, parsed_day)
                date_iso = parsed_date.strftime('%Y-%m-%d')

                return ParsedPayload(
                    name=name_part,
                    date=parsed_date,
                    date_iso=date_iso,
                    original_text=original_text
                )
            except ValueError:
                # Invalid date (e.g., Feb 30)
                return ParsedPayload(
                    name=name_part,
                    original_text=original_text,
                    needs_review=True
                )

        except ValueError:
            # Invalid numeric values
            return ParsedPayload(
                name=name_part,
                original_text=original_text,
                needs_review=True
            )

    def format_title(self, rule: RepairRule, payload: ParsedPayload) -> str:
        """Format the new title using the rule template"""
        try:
            # Calculate variables for template
            now = datetime.now()
            variables = {
                'name': payload.name,
                'label': payload.label or payload.name,
                'name_or_label': payload.label or payload.name,
                'date_display': '',
                'date_day_month': '',
                'date_iso': payload.date_iso or '',
                'age': '',
                'years_since': '',
                'age_suffix': '',
                'years_since_suffix': '',
                'warn_abs_days': ''
            }

            if payload.date:
                # Format date display
                variables['date_display'] = payload.date.strftime('%d.%m.%Y')
                variables['date_day_month'] = payload.date.strftime('%d.%m')

                # Calculate age/years since
                years_diff = now.year - payload.date.year
                if now.month < payload.date.month or (now.month == payload.date.month and now.day < payload.date.day):
                    years_diff -= 1

                variables['age'] = str(years_diff)
                variables['years_since'] = str(years_diff)

                # Add suffix if templates are provided and year is available
                if rule.age_suffix_template and payload.date.year:
                    variables['age_suffix'] = rule.age_suffix_template.format(age=years_diff)

                if rule.years_since_suffix_template and payload.date.year:
                    variables['years_since_suffix'] = rule.years_since_suffix_template.format(years_since=years_diff)

            # Handle warning offset
            if rule.warn_offset_days:
                variables['warn_abs_days'] = str(abs(rule.warn_offset_days))

            # Format the title
            formatted_title = rule.title_template.format(**variables)
            return formatted_title

        except Exception as e:
            self.logger.error(f"Error formatting title for rule {rule.id}: {e}")
            # Return a safe fallback
            return f"📅 {payload.name}"

    def calculate_signature(self, event: Dict[str, Any]) -> str:
        """Calculate event signature for idempotency checking"""
        signature_data = {
            'original_summary': event.get('summary', ''),
            'start': event.get('start', {}),
            'recurrence': event.get('recurrence', [])
        }

        signature_str = json.dumps(signature_data, sort_keys=True)
        return hashlib.sha256(signature_str.encode()).hexdigest()

    def needs_repair(self, event: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if event needs repair based on backend-agnostic idempotency markers

        Returns:
            (needs_repair, reason)
        """
        # Extract idempotency markers (backend-agnostic)
        chronos_markers = self._extract_chronos_markers(event)

        # Check if already cleaned
        marker_keys = self.idempotency_config.get('marker_keys', {})
        cleaned_key = marker_keys.get('cleaned', 'X-CHRONOS-CLEANED')

        if not chronos_markers.get('cleaned'):
            return True, "not_cleaned"

        # Check if signature changed
        stored_signature = chronos_markers.get('signature')
        current_signature = self.calculate_signature(event)

        if stored_signature != current_signature:
            return True, "signature_changed"

        return False, "already_cleaned"

    def _extract_chronos_markers(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Chronos idempotency markers from event (backend-agnostic)"""
        # First try to get from meta (unified format)
        meta = event.get('meta', {})
        chronos_markers = meta.get('chronos_markers', {})
        if chronos_markers:
            return chronos_markers

        # Fall back to Google Calendar extended properties format
        extended_props = event.get('extendedProperties', {})
        private_props = extended_props.get('private', {})

        markers = {}
        if 'chronos.cleaned' in private_props:
            markers['cleaned'] = private_props['chronos.cleaned']
        if 'chronos.rule_id' in private_props:
            markers['rule_id'] = private_props['chronos.rule_id']
        if 'chronos.signature' in private_props:
            markers['signature'] = private_props['chronos.signature']
        if 'chronos.original_summary' in private_props:
            markers['original_summary'] = private_props['chronos.original_summary']
        if 'chronos.payload' in private_props:
            markers['payload'] = private_props['chronos.payload']

        return markers

    def prepare_enrichment_data(self, rule: RepairRule, payload: ParsedPayload, event: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare enrichment data for KeywordEnricher plugin"""
        enrichment = {}

        if rule.enrich:
            enrichment.update(rule.enrich)

        # Add parsed payload data
        enrichment['parsed_payload'] = asdict(payload)
        enrichment['rule_id'] = rule.id
        enrichment['calendar_repaired'] = True

        # Add recurrence information if applicable
        if rule.rrule and payload.date:
            enrichment['recurrence_info'] = {
                'freq': 'YEARLY',
                'month': payload.date.month,
                'day': payload.date.day,
                'leap_day_policy': rule.leap_day_policy
            }

        return enrichment

    async def repair_event(self, event: Dict[str, Any], calendar) -> RepairResult:
        """
        Repair a single event

        Args:
            event: Normalized calendar event object
            calendar: CalendarRef object

        Returns:
            RepairResult with operation details
        """
        start_time = datetime.now()

        try:
            # Check if this is a keyword event
            event_title = event.get('summary', '')
            is_keyword, keyword, rule_id = self.is_keyword_event(event_title)

            if not is_keyword:
                return RepairResult(
                    success=True,
                    skipped=True,
                    elapsed_ms=(datetime.now() - start_time).total_seconds() * 1000
                )

            # Update metrics
            self.metrics['repair_attempt_total'][rule_id] = self.metrics['repair_attempt_total'].get(rule_id, 0) + 1

            # Check if repair is needed
            needs_repair, reason = self.needs_repair(event)
            if not needs_repair:
                return RepairResult(
                    success=True,
                    skipped=True,
                    rule_id=rule_id,
                    elapsed_ms=(datetime.now() - start_time).total_seconds() * 1000
                )

            # Parse the payload
            payload_text = event_title.split(':', 1)[1].strip()
            payload = self.parse_payload(payload_text, event_title)

            if payload.needs_review:
                return RepairResult(
                    success=True,
                    needs_review=True,
                    rule_id=rule_id,
                    error="ambiguous_parse",
                    elapsed_ms=(datetime.now() - start_time).total_seconds() * 1000
                )

            # Get the rule
            rule = self.rules[rule_id]

            # Format new title
            new_title = self.format_title(rule, payload)

            # Prepare enrichment data
            enrichment_data = self.prepare_enrichment_data(rule, payload, event)

            # Attempt to patch calendar backend
            patched = False
            etag_before = event.get('etag')
            etag_after = etag_before

            if self.source_manager:
                try:
                    patch_result = await self._patch_calendar_event(
                        calendar, event, new_title, payload, rule_id
                    )
                    patched = patch_result['patched']
                    etag_after = patch_result.get('etag_after', etag_before)

                except Exception as e:
                    self.logger.warning(f"Failed to patch calendar event {event.get('id')}: {e}")
                    # Continue with internal enrichment only
                    enrichment_data['source_readonly'] = True
                    self.metrics['readonly_skip_total'] += 1

            # Update success metrics
            self.metrics['repair_success_total'][rule_id] = self.metrics['repair_success_total'].get(rule_id, 0) + 1
            self.metrics['enrich_applied_total'][rule_id] = self.metrics['enrich_applied_total'].get(rule_id, 0) + 1

            return RepairResult(
                success=True,
                patched=patched,
                rule_id=rule_id,
                new_title=new_title,
                enrichment_data=enrichment_data,
                etag_before=etag_before,
                etag_after=etag_after,
                elapsed_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

        except Exception as e:
            self.logger.error(f"Error repairing event {event.get('id')}: {e}")
            return RepairResult(
                success=False,
                error=str(e),
                rule_id=rule_id if 'rule_id' in locals() else None,
                elapsed_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

    async def _patch_calendar_event(self, calendar, event: Dict[str, Any],
                                new_title: str, payload: ParsedPayload, rule_id: str) -> Dict[str, Any]:
        """
        Patch calendar event with new title and idempotency markers (backend-agnostic)

        Returns:
            Dictionary with 'patched' boolean and 'etag_after' if successful
        """
        if not self.source_manager:
            return {'patched': False}

        event_id = event['id']
        etag_before = event.get('etag')

        # Prepare patch data with unified idempotency markers
        patch_data = {
            'summary': new_title
        }

        # Add backend-agnostic idempotency markers
        marker_keys = self.idempotency_config.get('marker_keys', {})

        # Serialize payload with datetime support
        payload_dict = asdict(payload)
        # Convert datetime objects to ISO strings for JSON serialization
        for key, value in payload_dict.items():
            if isinstance(value, datetime):
                payload_dict[key] = value.isoformat()

        chronos_markers = {
            'cleaned': marker_keys.get('cleaned', 'true'),
            'rule_id': rule_id,
            'signature': self.calculate_signature(event),
            'original_summary': event.get('summary', ''),
            'payload': json.dumps(payload_dict)
        }

        patch_data['chronos_markers'] = chronos_markers

        # Patch the event via SourceAdapter
        try:
            adapter = self.source_manager.get_adapter()
            new_etag = await adapter.patch_event(
                calendar=calendar,
                event_id=event_id,
                patch_data=patch_data,
                if_match_etag=etag_before if getattr(self, 'use_if_match', True) else None
            )

            return {
                'patched': True,
                'etag_after': new_etag
            }

        except Exception as e:
            # Handle backend-agnostic errors
            if "conflict" in str(e).lower() or "412" in str(e) or "ConflictError" in str(type(e).__name__):
                self.metrics['repair_conflict_total']['etag_mismatch'] = \
                    self.metrics['repair_conflict_total'].get('etag_mismatch', 0) + 1
                self.logger.warning(f"ETag conflict for event {event_id}, skipping patch")
                return {'patched': False}
            elif "permission" in str(e).lower() or "PermissionError" in str(type(e).__name__):
                self.logger.warning(f"Permission denied for event {event_id} in calendar {calendar.alias}")
                return {'patched': False}

            raise e

    async def process_events(self, events: List[Dict[str, Any]], calendar) -> List[RepairResult]:
        """
        Process multiple events for repair

        Args:
            events: List of normalized calendar event objects
            calendar: CalendarRef object or calendar identifier (for backward compatibility)

        Returns:
            List of RepairResult objects
        """
        if not self.enabled:
            return [RepairResult(success=True, skipped=True) for _ in events]

        # Handle backward compatibility - if calendar is a string, try to get CalendarRef
        if isinstance(calendar, str):
            if self.source_manager:
                calendar_ref = await self.source_manager.get_calendar_by_id(calendar)
                if not calendar_ref:
                    self.logger.error(f"Calendar {calendar} not found in source manager")
                    return [RepairResult(success=False, error=f"Calendar {calendar} not found") for _ in events]
                calendar = calendar_ref
            else:
                self.logger.error("Source manager not available for calendar lookup")
                return [RepairResult(success=False, error="Source manager not available") for _ in events]

        results = []

        for event in events:
            try:
                result = await self.repair_event(event, calendar)
                results.append(result)

                # Log the operation
                self._log_repair_operation(event, result, calendar)

            except Exception as e:
                self.logger.error(f"Failed to process event {event.get('id')}: {e}")
                results.append(RepairResult(
                    success=False,
                    error=str(e)
                ))

        return results

    def _log_repair_operation(self, event: Dict[str, Any], result: RepairResult, calendar):
        """Log repair operation with structured context"""
        calendar_id = calendar.id if hasattr(calendar, 'id') else str(calendar)
        calendar_alias = calendar.alias if hasattr(calendar, 'alias') else calendar_id

        context = {
            'calendar_id': calendar_id,
            'calendar_alias': calendar_alias,
            'event_id': event.get('id'),
            'rule_id': result.rule_id,
            'etag_before': result.etag_before,
            'etag_after': result.etag_after,
            'elapsed_ms': result.elapsed_ms,
            'outcome': 'success' if result.success else 'error',
            'patched': result.patched,
            'skipped': result.skipped,
            'needs_review': result.needs_review,
            'readonly': result.readonly
        }

        if result.success:
            if result.skipped:
                self.logger.debug("Event repair skipped", extra=context)
            elif result.needs_review:
                self.logger.info("Event needs manual review", extra=context)
            elif result.patched:
                self.logger.info("Event successfully repaired and patched", extra=context)
            else:
                self.logger.info("Event repaired (internal only)", extra=context)
        else:
            context['error'] = result.error
            self.logger.error("Event repair failed", extra=context)

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics for monitoring"""
        return self.metrics.copy()

    def get_enrichment_data_for_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get enrichment data for a specific event
        This would be called by KeywordEnricher plugin
        """
        # In a real implementation, this would store enrichment data
        # and retrieve it when needed by subsequent plugins
        # For now, we'll integrate this into the event processing pipeline
        pass