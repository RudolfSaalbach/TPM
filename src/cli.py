#!/usr/bin/env python3
"""
Chronos CLI - Command Line Interface
"""

import asyncio
import click
import json
from pathlib import Path
from typing import List, Dict, Any

from src.core.calendar_client import GoogleCalendarClient
from src.core.event_parser import EventParser
from src.core.analytics_engine import AnalyticsEngine


@click.group()
def cli():
    """Chronos Engine Command Line Interface"""
    pass


@cli.command()
@click.option('--days', default=7, help='Number of days to sync')
def sync(days: int):
    """Sync calendar events"""
    
    async def run_sync():
        try:
            # Initialize components
            calendar = GoogleCalendarClient(
                credentials_file='config/credentials.json',
                token_file='config/token.json'
            )
            
            parser = EventParser()
            
            # Fetch and parse events
            events = await calendar.fetch_events(days_ahead=days)
            parsed_events = [parser.parse_event(event) for event in events]
            
            click.echo(f"Successfully synced {len(parsed_events)} events for {days} days")
            
            # Display summary
            for event in parsed_events[:5]:  # Show first 5
                click.echo(f"  - {event.title} [{event.priority.name}]")
            
            if len(parsed_events) > 5:
                click.echo(f"  ... and {len(parsed_events) - 5} more")
                
        except Exception as e:
            click.echo(f"Sync failed: {e}", err=True)
            raise click.Abort()
    
    asyncio.run(run_sync())


@cli.command()
@click.option('--output', default='analytics_report.json', help='Output file')
def analytics(output: str):
    """Generate analytics report"""
    
    async def run_analytics():
        try:
            analytics = AnalyticsEngine(cache_dir='data/analytics')
            
            # Generate report
            report = await analytics.generate_productivity_report()
            
            # Save to file
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            click.echo(f"Analytics report saved to {output}")
            
        except Exception as e:
            click.echo(f"Analytics generation failed: {e}", err=True)
            raise click.Abort()
    
    asyncio.run(run_analytics())


@cli.command()
def status():
    """Show system status"""
    
    # Check required directories
    dirs = ['logs', 'data', 'config', 'templates', 'static']
    
    click.echo("Chronos Engine Status:")
    click.echo("=" * 30)
    
    for directory in dirs:
        path = Path(directory)
        status = "✓" if path.exists() else "✗"
        click.echo(f"{status} {directory}/")
    
    # Check config files
    config_files = ['config/credentials.json', 'config/token.json', 'config/chronos.yaml']
    
    click.echo("\nConfiguration Files:")
    for config_file in config_files:
        path = Path(config_file)
        status = "✓" if path.exists() else "✗"
        click.echo(f"{status} {config_file}")


if __name__ == '__main__':
    cli()
