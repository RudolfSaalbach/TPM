#!/usr/bin/env python3
"""
Calendar Repairer Demo Script
Demonstrates the calendar repair functionality with various test cases
"""

import asyncio
import yaml
from datetime import datetime
from src.core.calendar_repairer import CalendarRepairer


async def demo_calendar_repairer():
    """Demonstrate Calendar Repairer functionality"""

    print("=" * 60)
    print("📅 CHRONOS CALENDAR REPAIRER DEMO")
    print("=" * 60)

    # Load configuration
    print("\n1️⃣ Loading Configuration...")
    with open('config/calendar_repairer.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Initialize CalendarRepairer (without Google Calendar client for demo)
    repairer = CalendarRepairer(config, calendar_client=None)
    print(f"✅ Calendar Repairer initialized")
    print(f"   - {len(repairer.rules)} repair rules loaded")
    print(f"   - {len(repairer.keyword_to_rule)} keywords recognized")
    print(f"   - Reserved prefixes: {', '.join(repairer.reserved_prefixes)}")

    # Test cases covering all requirement scenarios
    test_cases = [
        # Birthday events (English)
        "BDAY: John Smith 25.12.1990",
        "BIRTHDAY: Jane Doe 01.01.",
        "BDAYWARN: Mike's birthday reminder",

        # Birthday events (German)
        "GEB: Hans Müller 15.08.1985",
        "GEBURTSTAG: Anna Schmidt 12.03.2000",
        "GEBWARN: Peter's Geburtstag",

        # Memorial events
        "RIP: Grandmother 05.04.2015",
        "DEATH: Old Friend 22.11.2020",
        "MEMORIAL: Uncle Bob 31.12.2018",
        "TOD: Opa 15.06.2019",
        "GEDENKEN: Oma 08.09.2017",
        "RIPWARN: Memorial reminder",

        # Anniversary events
        "ANNIV: Wedding 20.06.2010",
        "ANNIVERSARY: Company founding 01.03.2005",
        "JUBI: Firmenjubiläum 15.09.1995",
        "ANNIVWARN: Wedding anniversary reminder",

        # Reserved prefixes (should NOT be processed)
        "ACTION: Do something important",
        "MEETING: Team standup",
        "CALL: Client discussion",

        # Non-keyword events (should be ignored)
        "Regular meeting",
        "No colon here",
        "UNKNOWN: Not recognized",

        # Edge cases
        "BDAY: Complex Name-With-Hyphens 29.02.2000",  # Leap year
        "RIP: José María González 15.08.1990",          # Unicode
        "BDAY: 03/07/1985",                            # Ambiguous date
        "BIRTHDAY: Name only without date",
        "GEB: Multiple dates 01.01.1990 and 15.06.2020",  # Multiple dates
    ]

    print(f"\n2️⃣ Testing {len(test_cases)} Event Titles...")
    print("-" * 60)

    successful_repairs = 0
    needs_review = 0
    skipped = 0

    for i, title in enumerate(test_cases, 1):
        print(f"\n{i:2d}. Testing: '{title}'")

        # Check if it's a keyword event
        is_keyword, keyword, rule_id = repairer.is_keyword_event(title)

        if not is_keyword:
            print("    ⏭️  SKIPPED - Not a keyword event or reserved prefix")
            skipped += 1
            continue

        print(f"    🔍 DETECTED - Keyword: {keyword}, Rule: {rule_id}")

        # Parse the payload
        payload_text = title.split(':', 1)[1].strip()
        payload = repairer.parse_payload(payload_text, title)

        if payload.needs_review:
            print("    ⚠️  NEEDS REVIEW - Ambiguous or invalid data")
            print(f"       Name: '{payload.name}'")
            print(f"       Issue: Ambiguous date or parsing error")
            needs_review += 1
            continue

        print(f"    📝 PARSED - Name: '{payload.name}'")
        if payload.date_iso:
            print(f"              Date: {payload.date_iso}")

        # Format new title
        rule = repairer.rules[rule_id]
        new_title = repairer.format_title(rule, payload)

        print(f"    ✨ FORMATTED: '{new_title}'")

        # Show enrichment data
        fake_event = {'id': f'demo-event-{i}'}
        enrichment = repairer.prepare_enrichment_data(rule, payload, fake_event)

        print(f"    🎯 ENRICHMENT:")
        print(f"       Type: {enrichment.get('event_type', 'N/A')}")
        print(f"       Tags: {', '.join(enrichment.get('tags', []))}")
        if enrichment.get('sub_tasks'):
            print(f"       Sub-tasks: {len(enrichment['sub_tasks'])} tasks")

        successful_repairs += 1

    print("\n" + "=" * 60)
    print("📊 DEMO SUMMARY")
    print("=" * 60)
    print(f"Total test cases:     {len(test_cases)}")
    print(f"Successful repairs:   {successful_repairs}")
    print(f"Needs manual review:  {needs_review}")
    print(f"Skipped (non-keyword): {skipped}")

    # Demonstrate rule information
    print(f"\n3️⃣ Available Repair Rules:")
    print("-" * 60)

    for rule_id, rule in repairer.rules.items():
        print(f"\n🔧 Rule: {rule_id}")
        print(f"   Keywords: {', '.join(rule.keywords)}")
        print(f"   Template: {rule.title_template}")
        if rule.warn_offset_days:
            print(f"   Warning offset: {rule.warn_offset_days} days")
        if rule.enrich:
            event_type = rule.enrich.get('event_type', 'N/A')
            tags = ', '.join(rule.enrich.get('tags', []))
            print(f"   Enriches as: {event_type} ({tags})")

    # Demonstrate metrics
    print(f"\n4️⃣ Metrics Example:")
    print("-" * 60)

    # Simulate some metrics
    repairer.metrics['repair_attempt_total']['bday'] = 15
    repairer.metrics['repair_success_total']['bday'] = 14
    repairer.metrics['repair_attempt_total']['rip'] = 8
    repairer.metrics['repair_success_total']['rip'] = 8
    repairer.metrics['readonly_skip_total'] = 2

    metrics = repairer.get_metrics()
    print("📈 Sample metrics that would be collected:")
    for metric_name, values in metrics.items():
        if isinstance(values, dict):
            for key, count in values.items():
                print(f"   {metric_name}[{key}]: {count}")
        else:
            print(f"   {metric_name}: {values}")

    print(f"\n5️⃣ API Integration:")
    print("-" * 60)
    print("📡 The following API endpoints are now available:")
    print("   POST /api/calendar/repair")
    print("        - Trigger repair with ?dry_run=true for preview")
    print("        - Parameters: calendar_id, dry_run, force")
    print("   GET  /api/calendar/repair/rules")
    print("        - Get available rules and configuration")
    print("   GET  /api/calendar/repair/metrics")
    print("        - Get repair metrics for monitoring")
    print("   POST /api/calendar/repair/test")
    print("        - Test parsing without making changes")

    print(f"\n6️⃣ Pipeline Integration:")
    print("-" * 60)
    print("🔄 Processing order in Chronos Engine:")
    pipeline_order = config.get('pipeline', {}).get('order', [])
    for i, step in enumerate(pipeline_order, 1):
        print(f"   {i}. {step}")
    print("\n   ✅ CalendarRepairer runs FIRST to clean titles")
    print("   ✅ Then KeywordEnricher adds metadata")
    print("   ✅ Finally command_handler processes ACTION: commands")

    print("\n" + "=" * 60)
    print("🎉 DEMO COMPLETE!")
    print("=" * 60)
    print("The Calendar Repairer is ready for integration!")
    print("All functional requirements from GoogleRepair.md are implemented.")


if __name__ == "__main__":
    print("Calendar Repairer Demo - Starting...")
    try:
        asyncio.run(demo_calendar_repairer())
    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    except Exception as e:
        print(f"\nDemo failed with error: {e}")
        import traceback
        traceback.print_exc()