"""full-text index over transcript lines

Revision ID: c5e8a1f3d920
Revises: a8e1d5c3b790
Create Date: 2026-11-11

An external-content FTS5 table over transcript_lines.text, kept in sync by triggers and
filled from the existing lines here. Additive: transcript_lines itself is unchanged. A
later migration that rebuilds transcript_lines (batch_alter_table copies the table and
drops its triggers) must recreate the triggers and rebuild the index. See
docs/search.md.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c5e8a1f3d920'
down_revision: Union[str, Sequence[str], None] = 'a8e1d5c3b790'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# unicode61 folds case for every script; remove_diacritics 2 lets "cafe" find "café".
CREATE_INDEX = """
CREATE VIRTUAL TABLE transcript_search USING fts5(
    text,
    content='transcript_lines',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
)
"""

TRIGGERS = (
    """
    CREATE TRIGGER transcript_search_insert AFTER INSERT ON transcript_lines BEGIN
        INSERT INTO transcript_search(rowid, text) VALUES (new.rowid, new.text);
    END
    """,
    """
    CREATE TRIGGER transcript_search_delete AFTER DELETE ON transcript_lines BEGIN
        INSERT INTO transcript_search(transcript_search, rowid, text)
        VALUES ('delete', old.rowid, old.text);
    END
    """,
    """
    CREATE TRIGGER transcript_search_update AFTER UPDATE OF text ON transcript_lines BEGIN
        INSERT INTO transcript_search(transcript_search, rowid, text)
        VALUES ('delete', old.rowid, old.text);
        INSERT INTO transcript_search(rowid, text) VALUES (new.rowid, new.text);
    END
    """,
)


def upgrade() -> None:
    op.execute(CREATE_INDEX)
    for trigger in TRIGGERS:
        op.execute(trigger)
    op.execute("INSERT INTO transcript_search(transcript_search) VALUES ('rebuild')")


def downgrade() -> None:
    for name in ('transcript_search_update', 'transcript_search_delete', 'transcript_search_insert'):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS transcript_search")
