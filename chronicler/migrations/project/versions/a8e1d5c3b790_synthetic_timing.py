"""record whether a transcript line's timings are real

Revision ID: a8e1d5c3b790
Revises: f6c3a9d2b417
Create Date: 2026-11-06

Existing rows keep a NULL flag. Readers fall back to treating a transcript as synthetic
when every start and end time is a whole number. See docs/transcription.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a8e1d5c3b790'
down_revision: Union[str, Sequence[str], None] = 'f6c3a9d2b417'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('transcript_lines') as batch:
        batch.add_column(sa.Column('synthetic_timing', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('transcript_lines') as batch:
        batch.drop_column('synthetic_timing')
