"""audio_sources

Revision ID: b3c7e1d94a02
Revises: a71eeb9c4240
Create Date: 2026-09-03 10:12:04.118392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c7e1d94a02'
down_revision: Union[str, Sequence[str], None] = 'a71eeb9c4240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audio_sources',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('filename', sa.String(length=1024), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('speaker_id', sa.String(length=36), nullable=True),
        sa.Column('transcription_state', sa.String(length=20), nullable=False),
        sa.Column('transcription_error', sa.String(), nullable=True),
        sa.Column('transcribed_at', sa.DateTime(), nullable=True),
        sa.Column('transcribed_hash', sa.String(length=64), nullable=True),
        sa.Column('transcription_language', sa.String(length=16), nullable=True),
        sa.Column('transcription_model', sa.String(length=64), nullable=True),
        sa.Column('normalization_state', sa.String(length=20), nullable=False),
        sa.Column('normalization_error', sa.String(), nullable=True),
        sa.Column('normalized_at', sa.DateTime(), nullable=True),
        sa.Column('normalized_hash', sa.String(length=64), nullable=True),
        sa.Column('normalized_filename', sa.String(length=1024), nullable=True),
        sa.Column('loudness_before', sa.Float(), nullable=True),
        sa.Column('loudness_after', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['speaker_id'], ['speakers.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('filename'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('audio_sources')
