"""
Alembic migration to add the pending_syncs table.
Run with: alembic revision --autogenerate -m "Add pending_syncs table"
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# Revision identifiers
revision = 'add_pending_syncs_001'
down_revision = None  # Update this with your previous migration
branch_labels = None
depends_on = None


def upgrade():
    """Create the pending_syncs table."""
    op.create_table(
        'pending_syncs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.String(36), nullable=False),
        sa.Column('operation_type', sa.String(20), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(36), nullable=False),
        sa.Column('db_data', sa.JSON(), nullable=True),
        sa.Column('api_data', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indices for better query performance
    op.create_index('ix_pending_syncs_transaction_id', 'pending_syncs', ['transaction_id'], unique=True)
    op.create_index('ix_pending_syncs_status', 'pending_syncs', ['status'])
    op.create_index('ix_pending_syncs_created_at', 'pending_syncs', ['created_at'])


def downgrade():
    """Drop the pending_syncs table."""
    op.drop_index('ix_pending_syncs_created_at', table_name='pending_syncs')
    op.drop_index('ix_pending_syncs_status', table_name='pending_syncs')
    op.drop_index('ix_pending_syncs_transaction_id', table_name='pending_syncs')
    op.drop_table('pending_syncs')
