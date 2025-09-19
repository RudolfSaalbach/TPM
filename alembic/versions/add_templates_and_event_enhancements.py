"""Add templates system and event enhancements

Revision ID: add_templates_and_event_enhancements
Revises: 2025_09_18_2302_307397805d0c
Create Date: 2025-09-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_templates_and_event_enhancements'
down_revision = '2025_09_18_2302_307397805d0c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to events table for enhanced filtering
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('start_utc', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('end_utc', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('all_day_date', sa.String(10), nullable=True))

        # Add indexes for performance
        batch_op.create_index('idx_events_start_utc', ['start_utc'])
        batch_op.create_index('idx_events_end_utc', ['end_utc'])
        batch_op.create_index('idx_events_all_day_date', ['all_day_date'])
        batch_op.create_index('idx_events_start_end', ['start_utc', 'end_utc'])

    # Create templates table
    op.create_table('templates',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('all_day', sa.Integer(), nullable=False, default=0),
        sa.Column('default_time', sa.Text(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('calendar_id', sa.Text(), nullable=True),
        sa.Column('tags_json', sa.Text(), nullable=False, default='[]'),
        sa.Column('usage_count', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.Column('author', sa.Text(), nullable=True),
    )

    # Create index on templates.title for search performance
    op.create_index('idx_templates_title', 'templates', ['title'])

    # Create template_usage table
    op.create_table('template_usage',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('used_at', sa.Text(), nullable=False),
        sa.Column('actor', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='CASCADE'),
    )

    # Create composite index for template usage queries
    op.create_index('idx_template_usage_template_used', 'template_usage', ['template_id', 'used_at'])


def downgrade() -> None:
    # Remove template tables
    op.drop_table('template_usage')
    op.drop_table('templates')

    # Remove event table enhancements
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index('idx_events_start_end')
        batch_op.drop_index('idx_events_all_day_date')
        batch_op.drop_index('idx_events_end_utc')
        batch_op.drop_index('idx_events_start_utc')

        batch_op.drop_column('all_day_date')
        batch_op.drop_column('end_utc')
        batch_op.drop_column('start_utc')