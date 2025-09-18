"""Initial Chronos Engine schema

Revision ID: 2025_01_01_0001
Revises: 
Create Date: 2025-01-01 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import JSON

# revision identifiers, used by Alembic.
revision: str = '2025_01_01_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema for Chronos Engine"""
    
    # Create events table
    op.create_table('events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False, default=''),
        sa.Column('description', sa.Text(), default=''),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('priority', sa.String(10), nullable=False, default='MEDIUM'),
        sa.Column('event_type', sa.String(20), nullable=False, default='TASK'),
        sa.Column('status', sa.String(20), nullable=False, default='SCHEDULED'),
        sa.Column('calendar_id', sa.String(100), default=''),
        sa.Column('attendees', JSON(), default=list),
        sa.Column('location', sa.String(200), default=''),
        sa.Column('tags', JSON(), default=list),
        sa.Column('estimated_duration', sa.Integer(), nullable=True),
        sa.Column('actual_duration', sa.Integer(), nullable=True),
        sa.Column('preparation_time', sa.Integer(), default=300),
        sa.Column('buffer_time', sa.Integer(), default=600),
        sa.Column('productivity_score', sa.Float(), nullable=True),
        sa.Column('completion_rate', sa.Float(), nullable=True),
        sa.Column('stress_level', sa.Float(), nullable=True),
        sa.Column('min_duration', sa.Integer(), default=900),
        sa.Column('max_duration', sa.Integer(), default=14400),
        sa.Column('flexible_timing', sa.Boolean(), default=True),
        sa.Column('requires_focus', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now())
    )
    
    # Create analytics_data table
    op.create_table('analytics_data',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_id', sa.String(36), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('metrics', JSON(), default=dict),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now())
    )
    
    # Create tasks table
    op.create_table('tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('function_name', sa.String(100), nullable=False),
        sa.Column('args', JSON(), default=list),
        sa.Column('kwargs', JSON(), default=dict),
        sa.Column('priority', sa.String(10), nullable=False, default='MEDIUM'),
        sa.Column('status', sa.String(20), nullable=False, default='PENDING'),
        sa.Column('result', JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True)
    )
    
    # Create indexes for performance
    op.create_index('ix_events_start_time', 'events', ['start_time'])
    op.create_index('ix_events_status', 'events', ['status'])
    op.create_index('ix_events_priority', 'events', ['priority'])
    op.create_index('ix_analytics_event_id', 'analytics_data', ['event_id'])
    op.create_index('ix_analytics_date', 'analytics_data', ['date'])
    op.create_index('ix_tasks_status', 'tasks', ['status'])
    op.create_index('ix_tasks_created_at', 'tasks', ['created_at'])


def downgrade() -> None:
    """Drop all tables"""
    op.drop_index('ix_tasks_created_at', table_name='tasks')
    op.drop_index('ix_tasks_status', table_name='tasks')
    op.drop_index('ix_analytics_date', table_name='analytics_data')
    op.drop_index('ix_analytics_event_id', table_name='analytics_data')
    op.drop_index('ix_events_priority', table_name='events')
    op.drop_index('ix_events_status', table_name='events')
    op.drop_index('ix_events_start_time', table_name='events')
    op.drop_table('tasks')
    op.drop_table('analytics_data')
    op.drop_table('events')
