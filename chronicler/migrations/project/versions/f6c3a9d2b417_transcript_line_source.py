"""link transcript lines to the audio source that produced them

Revision ID: f6c3a9d2b417
Revises: e5b2f70c31a8
Create Date: 2026-11-06

Existing lines keep a NULL source_id: nothing records which track they came from. See
docs/audio-sources.md for how the transcribe handler treats them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f6c3a9d2b417'
down_revision: Union[str, Sequence[str], None] = 'e5b2f70c31a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite cannot add a foreign key in place, so batch mode rebuilds the table.
    with op.batch_alter_table('transcript_lines') as batch:
        batch.add_column(sa.Column('source_id', sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            'fk_transcript_lines_source_id', 'audio_sources', ['source_id'], ['id']
        )
    with op.batch_alter_table('audio_sources') as batch:
        batch.add_column(
            sa.Column('start_offset', sa.Float(), nullable=False, server_default='0')
        )


def downgrade() -> None:
    with op.batch_alter_table('audio_sources') as batch:
        batch.drop_column('start_offset')
    with op.batch_alter_table('transcript_lines') as batch:
        batch.drop_constraint('fk_transcript_lines_source_id', type_='foreignkey')
        batch.drop_column('source_id')
