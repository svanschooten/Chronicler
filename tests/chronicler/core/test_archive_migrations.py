"""Upgrading an existing workspace's chronicler.db to the current schema."""

import sqlite3
from contextlib import closing

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from chronicler.core.database_manager import _MIGRATIONS_ROOT, DatabaseManager
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteKnownSpeakerRepository

BEFORE_UNUSED_COLUMNS_DROPPED = "b4d7e2a9c156"
CHRONICLE = "00000000-0000-0000-0000-000000000001"
TAG = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"
SPEAKER = "00000000-0000-0000-0000-000000000004"


def _archive_db_at(path, revision: str) -> None:
    """A chronicler.db migrated only as far as `revision`, as an older release left it."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        cfg = Config()
        cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / "archive"))
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)
    engine.dispose()


def _columns(connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


@pytest.mark.asyncio
async def test_rows_survive_dropping_the_unused_columns(tmp_path):
    archive_db = tmp_path / "chronicler.db"
    _archive_db_at(archive_db, BEFORE_UNUSED_COLUMNS_DROPPED)
    with closing(sqlite3.connect(archive_db)) as connection, connection:
        connection.execute(
            "INSERT INTO chronicles (id, title, kind, status, created_at, updated_at, "
            "source_file, speakers_count) "
            "VALUES (?, 'Session 1', 'Unknown', 'Imported', '2026-01-01', '2026-01-01', "
            "'/old/audio.mp3', 2)",
            (CHRONICLE,),
        )
        connection.execute("INSERT INTO tags (id, name) VALUES (?, 'Transcript')", (TAG,))
        connection.execute(
            "INSERT INTO chronicle_tags (chronicle_id, tag_id) VALUES (?, ?)", (CHRONICLE, TAG)
        )
        connection.execute(
            "INSERT INTO tasks (id, type, status, priority, progress, created_at, updated_at, "
            "chronicle_id, attempts, max_attempts) "
            "VALUES (?, 'TRANSCRIBE', 'DONE', 0, 100, '2026-01-01', '2026-01-01', ?, 1, 3)",
            (TASK, CHRONICLE),
        )
        connection.execute(
            "INSERT INTO known_speakers (id, name, normalized_name, uses, first_seen, "
            "last_used) VALUES (?, 'Alice', 'alice', 3, '2026-01-01', '2026-01-02')",
            (SPEAKER,),
        )

    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()
        async with db_manager.get_archive_session() as session:
            chronicle = await SQLiteChronicleRepository(session).get_by_id(CHRONICLE)
            speakers = SQLiteKnownSpeakerRepository(session)
            # The rebuilt table keeps its unique normalized name: no second Alice.
            await speakers.register("ALICE")
            names = await speakers.list_names()
    finally:
        await db_manager.close_all()

    assert chronicle is not None
    assert (chronicle.title, chronicle.speakers_count) == ("Session 1", 2)
    assert [tag.name for tag in chronicle.tags] == ["Transcript"]
    assert names == ["Alice"]

    with closing(sqlite3.connect(archive_db)) as connection:
        assert "source_file" not in _columns(connection, "chronicles")
        assert not {"uses", "first_seen", "last_used"} & _columns(connection, "known_speakers")
        task_keys = {row[2] for row in connection.execute("PRAGMA foreign_key_list(tasks)")}
        tag_keys = {row[2] for row in connection.execute("PRAGMA foreign_key_list(chronicle_tags)")}
        (task_chronicle,) = connection.execute("SELECT chronicle_id FROM tasks").fetchone()

    assert task_keys == {"chronicles"}
    assert tag_keys == {"chronicles", "tags"}
    assert task_chronicle == CHRONICLE


def test_the_migration_can_be_undone(tmp_path):
    archive_db = tmp_path / "chronicler.db"
    _archive_db_at(archive_db, "head")
    with closing(sqlite3.connect(archive_db)) as connection, connection:
        connection.execute(
            "INSERT INTO known_speakers (id, name, normalized_name) VALUES (?, 'Bob', 'bob')",
            (SPEAKER,),
        )

    engine = create_engine(f"sqlite:///{archive_db}")
    with engine.begin() as connection:
        cfg = Config()
        cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / "archive"))
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, BEFORE_UNUSED_COLUMNS_DROPPED)
    engine.dispose()

    with closing(sqlite3.connect(archive_db)) as connection:
        assert "source_file" in _columns(connection, "chronicles")
        row = connection.execute("SELECT name, uses FROM known_speakers").fetchone()
    assert row == ("Bob", 0)
