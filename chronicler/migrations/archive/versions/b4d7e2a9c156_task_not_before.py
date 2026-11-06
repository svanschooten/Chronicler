"""tasks.not_before, so a retry can wait

Revision ID: b4d7e2a9c156
Revises: c9f2a4e17b30
Create Date: 2026-11-06

Existing rows keep a NULL, which means claimable now. See docs/tasks.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b4d7e2a9c156'
down_revision: Union[str, Sequence[str], None] = 'c9f2a4e17b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('not_before', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('not_before')
