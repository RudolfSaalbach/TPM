"""Add v2.2 features: sub_tasks, event_links, workflows

Revision ID: 2025_09_19_001
Revises: 2025_09_18_2302_307397805d0c_merge_multiple_migration_heads
Create Date: 2025-09-19 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import JSON

# revision identifiers, used by Alembic.
revision: str = '2025_09_19_001'
down_revision: Union[str, None] = '2025_09_18_2302_307397805d0c_merge_multiple_migration_heads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add v2.2 features"""

    # Add sub_tasks column to events table (JSON field for checklists)
    op.add_column('events', sa.Column('sub_tasks', JSON(), nullable=True))

    # Add UTC timestamp fields for enhanced filtering
    op.add_column('events', sa.Column('start_utc', sa.DateTime(), nullable=True))
    op.add_column('events', sa.Column('end_utc', sa.DateTime(), nullable=True))
    op.add_column('events', sa.Column('all_day_date', sa.String(10), nullable=True))

    # Create indexes for new timestamp fields
    op.create_index('ix_events_start_utc', 'events', ['start_utc'])
    op.create_index('ix_events_end_utc', 'events', ['end_utc'])
    op.create_index('ix_events_all_day_date', 'events', ['all_day_date'])

    # Create event_links table for n:m event relationships
    op.create_table('event_links',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('source_event_id', sa.String(36), nullable=False),
        sa.Column('target_event_id', sa.String(36), nullable=False),
        sa.Column('link_type', sa.String(50), nullable=False, default='related'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('created_by', sa.String(100), nullable=True)
    )

    # Create indexes for event_links
    op.create_index('ix_event_links_source', 'event_links', ['source_event_id'])
    op.create_index('ix_event_links_target', 'event_links', ['target_event_id'])
    op.create_index('ix_event_links_type', 'event_links', ['link_type'])

    # Create unique constraint to prevent duplicate links
    op.create_unique_constraint(
        'uq_event_links_source_target_type',
        'event_links',
        ['source_event_id', 'target_event_id', 'link_type']
    )

    # Create action_workflows table for rule-based workflows
    op.create_table('action_workflows',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('trigger_command', sa.String(100), nullable=False),
        sa.Column('trigger_system', sa.String(100), nullable=False),
        sa.Column('follow_up_command', sa.String(100), nullable=False),
        sa.Column('follow_up_system', sa.String(100), nullable=False),
        sa.Column('follow_up_params', JSON(), nullable=True),
        sa.Column('delay_seconds', sa.Integer(), default=0),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now())
    )

    # Create indexes for action_workflows
    op.create_index('ix_workflows_trigger', 'action_workflows', ['trigger_command', 'trigger_system'])
    op.create_index('ix_workflows_enabled', 'action_workflows', ['enabled'])


def downgrade() -> None:
    """Remove v2.2 features"""

    # Drop action_workflows table
    op.drop_index('ix_workflows_enabled', table_name='action_workflows')
    op.drop_index('ix_workflows_trigger', table_name='action_workflows')
    op.drop_table('action_workflows')

    # Drop event_links table
    op.drop_constraint('uq_event_links_source_target_type', 'event_links', type_='unique')
    op.drop_index('ix_event_links_type', table_name='event_links')
    op.drop_index('ix_event_links_target', table_name='event_links')
    op.drop_index('ix_event_links_source', table_name='event_links')
    op.drop_table('event_links')

    # Drop new indexes from events table
    op.drop_index('ix_events_all_day_date', table_name='events')
    op.drop_index('ix_events_end_utc', table_name='events')
    op.drop_index('ix_events_start_utc', table_name='events')

    # Drop new columns from events table
    op.drop_column('events', 'all_day_date')
    op.drop_column('events', 'end_utc')
    op.drop_column('events', 'start_utc')
    op.drop_column('events', 'sub_tasks')