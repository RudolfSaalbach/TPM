"""merge multiple migration heads

Revision ID: 307397805d0c
Revises: 2025_01_01_0001, add_pending_syncs_001
Create Date: 2025-09-18 23:02:34.557243+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '307397805d0c'
down_revision: Union[str, None] = ('2025_01_01_0001', 'add_pending_syncs_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
