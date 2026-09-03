"""summaries

Revision ID: d4a81c62f9e5
Revises: b3c7e1d94a02
Create Date: 2026-09-03 17:41:09.223104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a81c62f9e5'
down_revision: Union[str, Sequence[str], None] = 'b3c7e1d94a02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'summaries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('model', sa.String(length=255), nullable=True),
        sa.Column('provider', sa.String(length=64), nullable=True),
        sa.Column('prompt_template', sa.String(), nullable=True),
        sa.Column('language', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('summaries')
