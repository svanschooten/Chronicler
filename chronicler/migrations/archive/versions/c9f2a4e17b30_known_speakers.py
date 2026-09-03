"""known_speakers

Revision ID: c9f2a4e17b30
Revises: 85f89d44ba85
Create Date: 2026-09-03 14:22:51.004913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f2a4e17b30'
down_revision: Union[str, Sequence[str], None] = '85f89d44ba85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'known_speakers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('normalized_name', sa.String(length=255), nullable=False),
        sa.Column('uses', sa.Integer(), nullable=False),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_used', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('normalized_name'),
    )
    op.create_index(
        op.f('ix_known_speakers_normalized_name'),
        'known_speakers',
        ['normalized_name'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_known_speakers_normalized_name'), table_name='known_speakers')
    op.drop_table('known_speakers')
