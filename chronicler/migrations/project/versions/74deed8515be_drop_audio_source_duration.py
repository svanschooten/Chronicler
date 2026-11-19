"""drop audio_sources.duration_seconds, which nothing ever wrote

Revision ID: 74deed8515be
Revises: c5e8a1f3d920
Create Date: 2026-11-18

A chronicle's duration comes from its transcript (see docs/processing.md), not from
this column. Batch mode rebuilds audio_sources only: transcript_lines, which carries the
search triggers, is left alone, so the search index needs no rebuild (see docs/search.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '74deed8515be'
down_revision: Union[str, Sequence[str], None] = 'c5e8a1f3d920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('audio_sources') as batch:
        batch.drop_column('duration_seconds')


def downgrade() -> None:
    with op.batch_alter_table('audio_sources') as batch:
        batch.add_column(sa.Column('duration_seconds', sa.Float(), nullable=True))
