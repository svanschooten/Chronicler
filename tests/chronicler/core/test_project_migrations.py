"""Upgrading an existing project.db to the current schema."""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from chronicler.core.database_manager import _MIGRATIONS_ROOT, DatabaseManager
from chronicler.core.sqlite import SQLiteAudioSourceRepository, SQLiteTranscriptRepository
from tests.projects import register_chronicle

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
        await register_chronicle(db_manager, "legacy", project_db)
        session = await db_manager.get_project_session("legacy")
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


@pytest.mark.asyncio
async def test_the_migration_attributes_lines_only_where_one_track_is_certain(tmp_path):
    """
    A speaker with exactly one transcribed track gets that track on their lines. Two
    transcribed tracks, none, or one that never finished leave the lines untracked.
    """
    project_db = tmp_path / "project.db"
    _project_db_at(project_db, BEFORE_SOURCE_IDS)

    def uid(n: int) -> str:
        return f"00000000-0000-0000-0000-{n:012d}"

    speakers = {"Alice": uid(11), "Bob": uid(12), "Carol": uid(13), "Dave": uid(14)}
    tracks = [
        (uid(21), "alice.wav", "Alice", "DONE"),
        (uid(22), "bob-1.wav", "Bob", "DONE"),
        (uid(23), "bob-2.wav", "Bob", "DONE"),
        (uid(24), "dave.wav", "Dave", "PENDING"),
    ]
    with sqlite3.connect(project_db) as connection:
        for index, (name, speaker_id) in enumerate(speakers.items()):
            connection.execute("INSERT INTO speakers (id, name) VALUES (?, ?)", (speaker_id, name))
            connection.execute(
                "INSERT INTO transcript_lines (id, speaker_id, start_time, end_time, text) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid(31 + index), speaker_id, float(index), float(index + 1), name),
            )
        for track_id, filename, speaker, state in tracks:
            connection.execute(
                "INSERT INTO audio_sources (id, filename, added_at, speaker_id, "
                "transcription_state, normalization_state) "
                "VALUES (?, ?, '2026-01-01', ?, ?, 'PENDING')",
                (track_id, filename, speakers[speaker], state),
            )

    db_manager = DatabaseManager(tmp_path / "workspace")
    try:
        await register_chronicle(db_manager, "legacy", project_db)
        session = await db_manager.get_project_session("legacy")
        async with session:
            lines = await SQLiteTranscriptRepository(session).get_lines()
    finally:
        await db_manager.close_all()

    assert {line.text: line.source_id and str(line.source_id) for line in lines} == {
        "Alice": uid(21),
        "Bob": None,
        "Carol": None,
        "Dave": None,
    }


def test_synthetic_timing_column_is_added_and_old_rows_stay_null(tmp_path):
    project_db = tmp_path / "project.db"
    _project_db_at(project_db, "f6c3a9d2b417")
    with sqlite3.connect(project_db) as connection:
        connection.execute(
            "INSERT INTO transcript_lines (id, start_time, end_time, text) "
            "VALUES (?, 0.0, 1.0, 'Hello')",
            (LINE,),
        )

    _project_db_at(project_db, "head")

    with sqlite3.connect(project_db) as connection:
        row = connection.execute("SELECT synthetic_timing FROM transcript_lines").fetchone()
    assert row == (None,)
