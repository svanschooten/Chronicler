"""drop the unused metadata table

Revision ID: e5b2f70c31a8
Revises: d4a81c62f9e5
Create Date: 2026-09-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5b2f70c31a8'
down_revision: Union[str, Sequence[str], None] = 'd4a81c62f9e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('metadata')


def downgrade() -> None:
    op.create_table(
        'metadata',
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
