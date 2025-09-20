"""
Calendar Repairer Plugin - Repairs keyword-prefixed events in Google Calendar
Pipeline: UndefinedGuard → CalendarRepairer → KeywordEnricher → command_handler

This plugin:
1. Parses keyword-prefixed events (BDAY:, RIP:, etc.)
2. Formats them into nice titles
3. Writes back to Google Calendar
4. Sets idempotency markers
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

    Processes keyword-prefixed events and repairs them in Google Calendar
    before any other processing takes place.
    """

    def __init__(self, config: Dict[str, Any], calendar_client=None):
        self.config = config.get('calendar_repairer', {})
        self.parsing_config = config.get('parsing', {})
        self.rules_config = config.get('rules', [])
        self.calendar_client = calendar_client
        self.logger = logging.getLogger(__name__)

        # Build rules lookup
        self.rules = self._build_rules()
        self.keyword_to_rule = self._build_keyword_lookup()

        # Configuration
        self.enabled = self.config.get('enabled', True)
        self.reserved_prefixes = set(
            prefix.upper() for prefix in self.config.get('reserved_prefixes', ['ACTION', 'MEETING', 'CALL'])
        )
        self.readonly_fallback = self.config.get('readonly_fallback', 'internal_enrich_only')

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
        Check if event needs repair based on idempotency markers

        Returns:
            (needs_repair, reason)
        """
        extended_props = event.get('extendedProperties', {})
        private_props = extended_props.get('private', {})

        # Check if already cleaned
        cleaned_marker = private_props.get(self.marker_key)
        if cleaned_marker != self.marker_value:
            return True, "not_cleaned"

        # Check if signature changed
        stored_signature = private_props.get('chronos.signature')
        current_signature = self.calculate_signature(event)

        if stored_signature != current_signature:
            return True, "signature_changed"

        return False, "already_cleaned"

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

    async def repair_event(self, event: Dict[str, Any], calendar_id: str) -> RepairResult:
        """
        Repair a single event

        Args:
            event: Google Calendar event object
            calendar_id: Calendar ID

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

            # Attempt to patch Google Calendar
            patched = False
            etag_before = event.get('etag')
            etag_after = etag_before

            if self.calendar_client:
                try:
                    patch_result = await self._patch_google_event(
                        calendar_id, event, new_title, payload, rule_id
                    )
                    patched = patch_result['patched']
                    etag_after = patch_result.get('etag_after', etag_before)

                except Exception as e:
                    self.logger.warning(f"Failed to patch Google Calendar event {event.get('id')}: {e}")
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

    async def _patch_google_event(self, calendar_id: str, event: Dict[str, Any],
                                new_title: str, payload: ParsedPayload, rule_id: str) -> Dict[str, Any]:
        """
        Patch Google Calendar event with new title and idempotency markers

        Returns:
            Dictionary with 'patched' boolean and 'etag_after' if successful
        """
        if not self.calendar_client:
            return {'patched': False}

        event_id = event['id']
        etag_before = event.get('etag')

        # Prepare patch data
        patch_data = {
            'summary': new_title
        }

        # Add idempotency markers
        extended_props = event.get('extendedProperties', {})
        private_props = extended_props.get('private', {})

        private_props.update({
            self.marker_key: self.marker_value,
            'chronos.rule_id': rule_id,
            'chronos.signature': self.calculate_signature(event),
            'chronos.original_summary': event.get('summary', ''),
            'chronos.payload': json.dumps(asdict(payload))
        })

        patch_data['extendedProperties'] = {
            'private': private_props
        }

        # Prepare headers
        headers = {}
        if self.use_if_match and etag_before:
            headers['If-Match'] = etag_before

        # Patch the event
        try:
            patched_event = await self.calendar_client.patch_event(
                calendar_id=calendar_id,
                event_id=event_id,
                event_data=patch_data,
                send_updates=self.send_updates,
                headers=headers
            )

            return {
                'patched': True,
                'etag_after': patched_event.get('etag')
            }

        except Exception as e:
            # Handle specific Google API errors
            if "412" in str(e):  # Precondition Failed
                self.metrics['repair_conflict_total']['etag_mismatch'] = \
                    self.metrics['repair_conflict_total'].get('etag_mismatch', 0) + 1
                self.logger.warning(f"ETag conflict for event {event_id}, skipping patch")
                return {'patched': False}

            raise e

    async def process_events(self, events: List[Dict[str, Any]], calendar_id: str) -> List[RepairResult]:
        """
        Process multiple events for repair

        Args:
            events: List of Google Calendar event objects
            calendar_id: Calendar ID

        Returns:
            List of RepairResult objects
        """
        if not self.enabled:
            return [RepairResult(success=True, skipped=True) for _ in events]

        results = []

        for event in events:
            try:
                result = await self.repair_event(event, calendar_id)
                results.append(result)

                # Log the operation
                self._log_repair_operation(event, result, calendar_id)

            except Exception as e:
                self.logger.error(f"Failed to process event {event.get('id')}: {e}")
                results.append(RepairResult(
                    success=False,
                    error=str(e)
                ))

        return results

    def _log_repair_operation(self, event: Dict[str, Any], result: RepairResult, calendar_id: str):
        """Log repair operation with structured context"""
        context = {
            'calendar_id': calendar_id,
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