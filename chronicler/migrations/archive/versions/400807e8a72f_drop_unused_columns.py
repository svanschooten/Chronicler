"""drop columns no feature uses

Revision ID: 400807e8a72f
Revises: b4d7e2a9c156
Create Date: 2026-11-18

chronicles.source_file predates audio sources: a chronicle's files live in its sources/
folder, and one column could not name several tracks anyway. known_speakers.uses,
first_seen and last_used were written and never read. Batch mode rebuilds both tables,
since SQLite cannot drop a column in place on every version Python ships with.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '400807e8a72f'
down_revision: Union[str, Sequence[str], None] = 'b4d7e2a9c156'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('chronicles') as batch:
        batch.drop_column('source_file')
    with op.batch_alter_table('known_speakers') as batch:
        batch.drop_column('uses')
        batch.drop_column('first_seen')
        batch.drop_column('last_used')


def downgrade() -> None:
    with op.batch_alter_table('known_speakers') as batch:
        batch.add_column(sa.Column('uses', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(
            sa.Column(
                'first_seen', sa.DateTime(), nullable=False, server_default=sa.func.now()
            )
        )
        batch.add_column(
            sa.Column(
                'last_used', sa.DateTime(), nullable=False, server_default=sa.func.now()
            )
        )
    with op.batch_alter_table('chronicles') as batch:
        batch.add_column(sa.Column('source_file', sa.String(length=1024), nullable=True))
