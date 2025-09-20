"""
Tests for Calendar Repairer Plugin
Validates all functional requirements from GoogleRepair.md
"""

import pytest
import yaml
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
from src.core.calendar_repairer import CalendarRepairer, ParsedPayload, RepairRule, RepairResult


class TestCalendarRepairer:
    """Test suite for Calendar Repairer functionality"""

    @pytest.fixture
    def test_config(self):
        """Load test configuration from YAML"""
        with open('config/calendar_repairer.yaml', 'r') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def mock_calendar_client(self):
        """Mock Google Calendar client"""
        client = Mock()
        client.patch_event = AsyncMock()
        return client

    @pytest.fixture
    def calendar_repairer(self, test_config, mock_calendar_client):
        """Create CalendarRepairer instance for testing"""
        return CalendarRepairer(test_config, mock_calendar_client)

    # KEYWORD DETECTION TESTS

    def test_keyword_detection_birthday_english(self, calendar_repairer):
        """Test birthday keyword detection in English"""
        test_cases = [
            ("BDAY: John Smith 25.12.1990", True, "BDAY", "bday"),
            ("BIRTHDAY: Jane Doe 01.01.", True, "BIRTHDAY", "bday"),
            ("bday: lowercase test", True, "BDAY", "bday"),  # Case insensitive
            ("Birthday:Mixed Case", True, "BIRTHDAY", "bday"),
        ]

        for title, expected_is_keyword, expected_keyword, expected_rule in test_cases:
            is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(title)
            assert is_keyword == expected_is_keyword, f"Failed for: {title}"
            assert keyword == expected_keyword, f"Failed keyword for: {title}"
            assert rule_id == expected_rule, f"Failed rule for: {title}"

    def test_keyword_detection_birthday_german(self, calendar_repairer):
        """Test birthday keyword detection in German"""
        test_cases = [
            ("GEB: Hans Müller 15.08.1985", True, "GEB", "bday"),
            ("GEBURTSTAG: Anna Schmidt 12.03.", True, "GEBURTSTAG", "bday"),
            ("geb: lowercase test", True, "GEB", "bday"),
        ]

        for title, expected_is_keyword, expected_keyword, expected_rule in test_cases:
            is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(title)
            assert is_keyword == expected_is_keyword, f"Failed for: {title}"
            assert keyword == expected_keyword, f"Failed keyword for: {title}"
            assert rule_id == expected_rule, f"Failed rule for: {title}"

    def test_keyword_detection_memorial(self, calendar_repairer):
        """Test memorial keyword detection"""
        test_cases = [
            ("RIP: Grandmother 05.04.2015", True, "RIP", "rip"),
            ("DEATH: Old Friend 22.11.2020", True, "DEATH", "rip"),
            ("MEMORIAL: Uncle Bob 31.12.2018", True, "MEMORIAL", "rip"),
            ("TOD: Opa 15.06.2019", True, "TOD", "rip"),
            ("GEDENKEN: Oma 08.09.2017", True, "GEDENKEN", "rip"),
        ]

        for title, expected_is_keyword, expected_keyword, expected_rule in test_cases:
            is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(title)
            assert is_keyword == expected_is_keyword, f"Failed for: {title}"
            assert keyword == expected_keyword, f"Failed keyword for: {title}"
            assert rule_id == expected_rule, f"Failed rule for: {title}"

    def test_keyword_detection_warnings(self, calendar_repairer):
        """Test warning keyword detection"""
        test_cases = [
            ("BDAYWARN: John's birthday reminder", True, "BDAYWARN", "bdaywarn"),
            ("RIPWARN: Memorial reminder", True, "RIPWARN", "ripwarn"),
            ("ANNIVWARN: Anniversary reminder", True, "ANNIVWARN", "annivwarn"),
        ]

        for title, expected_is_keyword, expected_keyword, expected_rule in test_cases:
            is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(title)
            assert is_keyword == expected_is_keyword, f"Failed for: {title}"
            assert keyword == expected_keyword, f"Failed keyword for: {title}"
            assert rule_id == expected_rule, f"Failed rule for: {title}"

    def test_reserved_prefixes_not_processed(self, calendar_repairer):
        """Test that reserved prefixes are never processed"""
        reserved_cases = [
            "ACTION: Do something important",
            "MEETING: Team standup",
            "CALL: Client discussion",
        ]

        for title in reserved_cases:
            is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(title)
            assert not is_keyword, f"Reserved prefix should not be processed: {title}"

    def test_non_keyword_events_ignored(self, calendar_repairer):
        """Test that non-keyword events are ignored"""
        non_keyword_cases = [
            "Regular meeting",
            "No colon here",
            "UNKNOWN: Not a recognized keyword",
            "INVALID:No space after colon",
            "",
        ]

        for title in non_keyword_cases:
            is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(title)
            assert not is_keyword, f"Should not be processed: {title}"

    # DATE PARSING TESTS

    def test_date_parsing_various_formats(self, calendar_repairer):
        """Test parsing different date formats"""
        test_cases = [
            # DD.MM.YYYY format
            ("John Smith 25.12.1990", "John Smith", "1990-12-25"),
            ("Jane Doe 01.01.2000", "Jane Doe", "2000-01-01"),

            # DD.MM. format (no year)
            ("Bob Test 15.03.", "Bob Test", f"{datetime.now().year}-03-15"),

            # DD-MM-YYYY format
            ("Alice Johnson 22-08-1995", "Alice Johnson", "1995-08-22"),

            # DD/MM/YYYY format
            ("Charlie Brown 30/06/1988", "Charlie Brown", "1988-06-30"),

            # Name only (no date)
            ("David Wilson", "David Wilson", None),

            # Complex names with dates
            ("Maria Elena Gonzalez 12.07.1992", "Maria Elena Gonzalez", "1992-07-12"),
        ]

        for payload, expected_name, expected_date in test_cases:
            result = calendar_repairer.parse_payload(payload, f"BDAY: {payload}")
            assert result.name == expected_name, f"Name mismatch for: {payload}"
            assert result.date_iso == expected_date, f"Date mismatch for: {payload}"
            assert not result.needs_review, f"Should not need review: {payload}"

    def test_date_parsing_ambiguous_dates(self, calendar_repairer):
        """Test handling of ambiguous dates when strict mode is enabled"""
        # CalendarRepairer has strict_when_ambiguous = True by default
        ambiguous_cases = [
            "John Smith 03/07/1990",  # Could be Mar 7 or Jul 3
            "Jane Doe 05/12/1985",    # Could be May 12 or Dec 5
        ]

        for payload in ambiguous_cases:
            result = calendar_repairer.parse_payload(payload, f"BDAY: {payload}")
            assert result.needs_review, f"Ambiguous date should need review: {payload}"

    def test_date_parsing_invalid_dates(self, calendar_repairer):
        """Test handling of invalid dates"""
        invalid_cases = [
            "John Smith 32.01.1990",  # Invalid day
            "Jane Doe 15.13.1990",    # Invalid month
            "Bob Test 29.02.1990",    # Invalid leap day
        ]

        for payload in invalid_cases:
            result = calendar_repairer.parse_payload(payload, f"BDAY: {payload}")
            assert result.needs_review, f"Invalid date should need review: {payload}"

    def test_date_parsing_edge_cases(self, calendar_repairer):
        """Test edge cases in date parsing"""
        edge_cases = [
            # Multiple dates - should use the last one
            ("John born 01.01.1990 moved 15.06.2020", "John born 01.01.1990 moved", "2020-06-15"),

            # Date at beginning
            ("15.03.1985 John Smith", "", "1985-03-15"),  # Name becomes empty

            # Just a date
            ("25.12.1990", "", "1990-12-25"),
        ]

        for payload, expected_name, expected_date in edge_cases:
            result = calendar_repairer.parse_payload(payload, f"BDAY: {payload}")
            # Handle empty name case
            expected_name = expected_name if expected_name else "Unknown"
            assert result.name == expected_name or result.name == "Unknown", f"Name handling for: {payload}"
            assert result.date_iso == expected_date, f"Date mismatch for: {payload}"

    # TITLE FORMATTING TESTS

    def test_birthday_title_formatting(self, calendar_repairer):
        """Test birthday title formatting"""
        rule = calendar_repairer.rules['bday']

        # With year (should include age)
        payload = ParsedPayload(
            name="John Smith",
            date=datetime(1990, 12, 25),
            date_iso="1990-12-25"
        )

        formatted = calendar_repairer.format_title(rule, payload)
        assert "🎉 Birthday: John Smith" in formatted
        assert "25.12.1990" in formatted
        assert "turns" in formatted  # Age suffix should be included

    def test_memorial_title_formatting(self, calendar_repairer):
        """Test memorial title formatting"""
        rule = calendar_repairer.rules['rip']

        payload = ParsedPayload(
            name="Grandmother",
            date=datetime(2015, 4, 5),
            date_iso="2015-04-05"
        )

        formatted = calendar_repairer.format_title(rule, payload)
        assert "🕯️ In memory of Grandmother" in formatted
        assert "05.04.2015" in formatted
        assert "†" in formatted

    def test_warning_title_formatting(self, calendar_repairer):
        """Test warning title formatting"""
        rule = calendar_repairer.rules['bdaywarn']

        payload = ParsedPayload(
            name="John Smith",
            date=datetime(1990, 12, 25),
            date_iso="1990-12-25"
        )

        formatted = calendar_repairer.format_title(rule, payload)
        assert "⏰" in formatted
        assert "John Smith's birthday" in formatted
        assert "4 days" in formatted  # Warn offset
        assert "25.12" in formatted

    def test_anniversary_title_formatting(self, calendar_repairer):
        """Test anniversary title formatting"""
        rule = calendar_repairer.rules['anniv']

        payload = ParsedPayload(
            name="Wedding Anniversary",
            label="Wedding",
            date=datetime(2010, 6, 15),
            date_iso="2010-06-15"
        )

        formatted = calendar_repairer.format_title(rule, payload)
        assert "🎖️" in formatted
        assert "Wedding" in formatted
        assert "15.06.2010" in formatted
        assert "since" in formatted

    # IDEMPOTENCY TESTS

    def test_idempotency_already_cleaned(self, calendar_repairer):
        """Test that already cleaned events are skipped"""
        event = {
            'id': 'test-event-1',
            'summary': 'BDAY: John Smith 25.12.1990',
            'extendedProperties': {
                'private': {
                    'chronos.cleaned': 'v1',
                    'chronos.signature': calendar_repairer.calculate_signature({
                        'summary': 'BDAY: John Smith 25.12.1990',
                        'start': {},
                        'recurrence': []
                    })
                }
            }
        }

        needs_repair, reason = calendar_repairer.needs_repair(event)
        assert not needs_repair
        assert reason == "already_cleaned"

    def test_idempotency_signature_changed(self, calendar_repairer):
        """Test that events with changed signatures are processed"""
        event = {
            'id': 'test-event-1',
            'summary': 'BDAY: Jane Doe 01.01.1995',  # Different content
            'extendedProperties': {
                'private': {
                    'chronos.cleaned': 'v1',
                    'chronos.signature': 'old-signature-hash'  # Different signature
                }
            }
        }

        needs_repair, reason = calendar_repairer.needs_repair(event)
        assert needs_repair
        assert reason == "signature_changed"

    def test_idempotency_not_cleaned(self, calendar_repairer):
        """Test that uncleaned events are processed"""
        event = {
            'id': 'test-event-1',
            'summary': 'BDAY: John Smith 25.12.1990',
            'extendedProperties': {
                'private': {}
            }
        }

        needs_repair, reason = calendar_repairer.needs_repair(event)
        assert needs_repair
        assert reason == "not_cleaned"

    # ENRICHMENT TESTS

    def test_enrichment_data_preparation(self, calendar_repairer):
        """Test enrichment data preparation for other plugins"""
        rule = calendar_repairer.rules['bday']
        payload = ParsedPayload(
            name="John Smith",
            date=datetime(1990, 12, 25),
            date_iso="1990-12-25"
        )
        event = {'id': 'test-event'}

        enrichment = calendar_repairer.prepare_enrichment_data(rule, payload, event)

        assert enrichment['event_type'] == 'birthday'
        assert 'personal' in enrichment['tags']
        assert 'birthday' in enrichment['tags']
        assert len(enrichment['sub_tasks']) > 0
        assert enrichment['rule_id'] == 'bday'
        assert enrichment['calendar_repaired'] is True
        assert 'recurrence_info' in enrichment

    # ERROR HANDLING TESTS

    @pytest.mark.asyncio
    async def test_google_patch_error_handling(self, calendar_repairer, mock_calendar_client):
        """Test error handling during Google Calendar patching"""
        # Simulate 412 Precondition Failed (ETag conflict)
        mock_calendar_client.patch_event.side_effect = Exception("412 Precondition Failed")

        event = {
            'id': 'test-event-1',
            'summary': 'BDAY: John Smith 25.12.1990',
            'etag': 'old-etag'
        }

        result = await calendar_repairer.repair_event(event, 'primary')

        # Should succeed but not be patched due to conflict
        assert result.success
        assert not result.patched
        assert result.rule_id == 'bday'

    @pytest.mark.asyncio
    async def test_readonly_calendar_fallback(self, calendar_repairer):
        """Test fallback behavior for read-only calendars"""
        # Set calendar_client to None to simulate read-only
        calendar_repairer.calendar_client = None

        event = {
            'id': 'test-event-1',
            'summary': 'BDAY: John Smith 25.12.1990'
        }

        result = await calendar_repairer.repair_event(event, 'primary')

        # Should succeed with enrichment but no patching
        assert result.success
        assert not result.patched
        assert result.enrichment_data is not None
        assert result.enrichment_data.get('source_readonly') is True

    # INTEGRATION TESTS

    @pytest.mark.asyncio
    async def test_end_to_end_birthday_repair(self, calendar_repairer, mock_calendar_client):
        """Test complete birthday event repair workflow"""
        # Mock successful Google Calendar patch
        mock_calendar_client.patch_event.return_value = {
            'etag': 'new-etag-value'
        }

        event = {
            'id': 'bday-event-1',
            'summary': 'BDAY: John Smith 25.12.1990',
            'etag': 'original-etag',
            'extendedProperties': {'private': {}}
        }

        result = await calendar_repairer.repair_event(event, 'primary')

        # Verify success
        assert result.success
        assert result.patched
        assert result.rule_id == 'bday'
        assert "🎉 Birthday: John Smith" in result.new_title
        assert result.enrichment_data is not None
        assert result.enrichment_data['event_type'] == 'birthday'

        # Verify Google Calendar was called
        mock_calendar_client.patch_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_processing(self, calendar_repairer, mock_calendar_client):
        """Test processing multiple events in batch"""
        mock_calendar_client.patch_event.return_value = {'etag': 'new-etag'}

        events = [
            {
                'id': 'event-1',
                'summary': 'BDAY: John Smith 25.12.1990',
                'extendedProperties': {'private': {}}
            },
            {
                'id': 'event-2',
                'summary': 'RIP: Grandmother 05.04.2015',
                'extendedProperties': {'private': {}}
            },
            {
                'id': 'event-3',
                'summary': 'Regular meeting',  # Not a keyword event
                'extendedProperties': {'private': {}}
            }
        ]

        results = await calendar_repairer.process_events(events, 'primary')

        assert len(results) == 3
        assert results[0].success and results[0].patched  # Birthday
        assert results[1].success and results[1].patched  # Memorial
        assert results[2].success and results[2].skipped  # Regular event

    def test_metrics_collection(self, calendar_repairer):
        """Test that metrics are properly collected"""
        # Simulate some operations
        calendar_repairer.metrics['repair_attempt_total']['bday'] = 5
        calendar_repairer.metrics['repair_success_total']['bday'] = 4
        calendar_repairer.metrics['readonly_skip_total'] = 1

        metrics = calendar_repairer.get_metrics()

        assert metrics['repair_attempt_total']['bday'] == 5
        assert metrics['repair_success_total']['bday'] == 4
        assert metrics['readonly_skip_total'] == 1

    # CONFIGURATION TESTS

    def test_configuration_loading(self, test_config):
        """Test that configuration is properly loaded"""
        repairer = CalendarRepairer(test_config, None)

        assert repairer.enabled is True
        assert 'ACTION' in repairer.reserved_prefixes
        assert repairer.day_first is True
        assert len(repairer.rules) > 0
        assert 'bday' in repairer.rules
        assert 'rip' in repairer.rules

    def test_rule_keyword_lookup(self, calendar_repairer):
        """Test that keyword lookup works correctly"""
        assert calendar_repairer.keyword_to_rule['BDAY'] == 'bday'
        assert calendar_repairer.keyword_to_rule['BIRTHDAY'] == 'bday'
        assert calendar_repairer.keyword_to_rule['GEB'] == 'bday'
        assert calendar_repairer.keyword_to_rule['GEBURTSTAG'] == 'bday'
        assert calendar_repairer.keyword_to_rule['RIP'] == 'rip'
        assert calendar_repairer.keyword_to_rule['MEMORIAL'] == 'rip'

    # STRESS AND PERFORMANCE TESTS

    def test_large_payload_parsing(self, calendar_repairer):
        """Test parsing very long event titles"""
        long_name = "A" * 200  # Very long name
        payload = f"{long_name} 25.12.1990"

        result = calendar_repairer.parse_payload(payload, f"BDAY: {payload}")
        assert result.name == long_name
        assert result.date_iso == "1990-12-25"

    def test_unicode_and_special_characters(self, calendar_repairer):
        """Test handling of Unicode and special characters"""
        test_cases = [
            "José María González 15.08.1990",
            "李小明 25.12.1985",
            "Müller-Schmidt 01.01.2000",
            "O'Connor 17.03.1995",
            "Jean-Pierre 29.02.1992",
        ]

        for payload in test_cases:
            result = calendar_repairer.parse_payload(payload, f"BDAY: {payload}")
            assert result.name in payload
            assert not result.needs_review, f"Should handle Unicode: {payload}"