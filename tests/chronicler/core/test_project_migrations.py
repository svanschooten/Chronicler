"""Upgrading an existing project.db to the current schema."""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from chronicler.core.database_manager import _MIGRATIONS_ROOT, DatabaseManager
from chronicler.core.sqlite import SQLiteAudioSourceRepository, SQLiteTranscriptRepository

BEFORE_SOURCE_IDS = "e5b2f70c31a8"
SPEAKER = "00000000-0000-0000-0000-000000000001"
LINE = "00000000-0000-0000-0000-000000000002"
SOURCE = "00000000-0000-0000-0000-000000000003"


def _project_db_at(path, revision: str) -> None:
    """A project.db migrated only as far as `revision`, as an older release left it."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        cfg = Config()
        cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / "project"))
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)
    engine.dispose()


@pytest.mark.asyncio
async def test_lines_and_sources_survive_the_source_id_migration(tmp_path):
    project_db = tmp_path / "project.db"
    _project_db_at(project_db, BEFORE_SOURCE_IDS)
    with sqlite3.connect(project_db) as connection:
        connection.execute("INSERT INTO speakers (id, name) VALUES (?, 'Alice')", (SPEAKER,))
        connection.execute(
            "INSERT INTO transcript_lines (id, speaker_id, start_time, end_time, text) "
            "VALUES (?, ?, 0.0, 1.0, 'Hello')",
            (LINE, SPEAKER),
        )
        connection.execute(
            "INSERT INTO audio_sources (id, filename, added_at, transcription_state, "
            "normalization_state) VALUES (?, 'alice.wav', '2026-01-01', 'DONE', 'PENDING')",
            (SOURCE,),
        )

    db_manager = DatabaseManager(tmp_path / "workspace")
    try:
        session = await db_manager.get_project_session("legacy", custom_path=project_db)
        async with session:
            (line,) = await SQLiteTranscriptRepository(session).get_lines()
            (source,) = await SQLiteAudioSourceRepository(session).list_sources()
            foreign_keys = (
                await session.execute(text("PRAGMA foreign_key_list(transcript_lines)"))
            ).all()

        assert (line.text, line.speaker_name, line.source_id) == ("Hello", "Alice", None)
        assert source.start_offset == 0.0
        assert {row[2] for row in foreign_keys} == {"speakers", "audio_sources"}
    finally:
        await db_manager.close_all()
