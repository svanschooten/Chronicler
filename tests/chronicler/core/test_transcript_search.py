"""Ticket 063: full-text search over transcripts, in one chronicle and across the workspace."""

import sqlite3
from contextlib import closing

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, update

from chronicler.core.database_manager import _MIGRATIONS_ROOT, DatabaseManager
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.project_database import DBTranscriptLine
from chronicler.core.services.transcript_service import (
    MATCHES_PER_CHRONICLE,
    TranscriptService,
)
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository
from chronicler.core.sqlite.patterns import fts_query
from tests.projects import register_chronicle

BEFORE_SEARCH = "a8e1d5c3b790"


def _line(text: str, start: float, speaker: str = "Alice") -> TranscriptLine:
    return TranscriptLine(speaker_name=speaker, text=text, start_time=start, end_time=start + 1)


async def _add_lines(db_manager, chronicle_id, *texts: str) -> None:
    async with db_manager.transaction(chronicle_id, must_exist=False) as session:
        repo = SQLiteTranscriptRepository(session)
        speaker = await repo.get_or_create_speaker("Alice")
        lines = [_line(text, float(index)) for index, text in enumerate(texts)]
        for line in lines:
            line.speaker_id = speaker.id
        await repo.add_lines(lines)


async def _search(db_manager, chronicle_id, query: str) -> list[str]:
    async with await db_manager.get_project_session(chronicle_id) as session:
        return [line.text for line in await SQLiteTranscriptRepository(session).search(query)]


class TestQuery:
    def test_every_word_is_required_and_the_last_is_a_prefix(self):
        assert fts_query("spoken phr") == '"spoken" "phr"*'

    @pytest.mark.parametrize("typed", ["", "   ", "!?", '"'])
    def test_text_with_no_words_searches_nothing(self, typed):
        assert fts_query(typed) is None

    def test_fts_syntax_is_read_as_words(self):
        assert fts_query('NEAR(a b) OR "x') == '"NEAR" "a" "b" "OR" "x"*'


class TestChronicleSearch:
    @pytest.mark.asyncio
    async def test_a_spoken_phrase_finds_its_line(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "c")
        await _add_lines(db_manager, "c", "Good morning", "We should discuss the budget", "Bye")

        assert await _search(db_manager, "c", "discuss the budget") == [
            "We should discuss the budget"
        ]
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_words_need_not_be_adjacent_and_order_follows_the_transcript(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "c")
        await _add_lines(db_manager, "c", "budget talk later", "Talk about the budget", "none")

        assert await _search(db_manager, "c", "budget talk") == [
            "budget talk later",
            "Talk about the budget",
        ]
        await db_manager.close_all()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("query", "line"),
        [
            ("CAFE", "We met at the café"),
            ("café", "We met at the cafe"),
            ("wor", "Hello world"),
            ("zürich", "Ich wohne in ZÜRICH"),
        ],
    )
    async def test_case_accents_and_prefixes_are_forgiven(self, tmp_path, query, line):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "c")
        await _add_lines(db_manager, "c", line)

        assert await _search(db_manager, "c", query) == [line]
        await db_manager.close_all()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", ['NEAR("', "a OR", "text:", "*", '"unbalanced'])
    async def test_fts_syntax_in_the_query_never_raises(self, tmp_path, query):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "c")
        await _add_lines(db_manager, "c", "plain text")

        await _search(db_manager, "c", query)
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_index_follows_edits_and_deletes(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "c")
        await _add_lines(db_manager, "c", "original words", "doomed line")

        async with db_manager.transaction("c", must_exist=False) as session:
            await session.execute(
                update(DBTranscriptLine)
                .where(DBTranscriptLine.text == "original words")
                .values(text="corrected words")
            )
            await SQLiteTranscriptRepository(session).delete_all_lines()
        await _add_lines(db_manager, "c", "corrected words")

        assert await _search(db_manager, "c", "original") == []
        assert await _search(db_manager, "c", "doomed") == []
        assert await _search(db_manager, "c", "corrected") == ["corrected words"]
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_existing_chronicle_is_indexed_when_it_is_upgraded(self, tmp_path):
        project_db = tmp_path / "older" / "project.db"
        project_db.parent.mkdir()
        engine = create_engine(f"sqlite:///{project_db}")
        with engine.begin() as connection:
            cfg = Config()
            cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / "project"))
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, BEFORE_SEARCH)
        engine.dispose()
        with closing(sqlite3.connect(project_db)) as connection, connection:
            connection.execute(
                "INSERT INTO transcript_lines (id, start_time, end_time, text) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 0, 1, "
                "'Recorded before search existed')"
            )

        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "older", project_db)

        assert await _search(db_manager, "older", "before search") == [
            "Recorded before search existed"
        ]
        await db_manager.close_all()


async def _workspace(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    chronicles = SQLiteChronicleRepository(session)
    return db_manager, session, chronicles, TranscriptService(db_manager, chronicles)


class TestWorkspaceSearch:
    @pytest.mark.asyncio
    async def test_finds_each_chronicle_and_its_lines(self, tmp_path):
        db_manager, session, chronicles, service = await _workspace(tmp_path)
        try:
            budget = await chronicles.create(Chronicle(title="Budget meeting"))
            standup = await chronicles.create(Chronicle(title="Standup"))
            await chronicles.create(Chronicle(title="Empty"))
            await _add_lines(db_manager, budget.id, "the budget is tight", "lunch")
            await _add_lines(db_manager, standup.id, "no budget news today")

            matches = await service.search_transcripts("budget")

            assert {match.chronicle.title for match in matches} == {"Budget meeting", "Standup"}
            by_title = {match.chronicle.title: match for match in matches}
            assert [line.text for line in by_title["Budget meeting"].lines] == [
                "the budget is tight"
            ]
            assert not by_title["Budget meeting"].has_more
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_chronicle_with_many_matches_shows_a_few_and_says_there_are_more(
        self, tmp_path
    ):
        db_manager, session, chronicles, service = await _workspace(tmp_path)
        try:
            chronicle = await chronicles.create(Chronicle(title="Talkative"))
            await _add_lines(db_manager, chronicle.id, *[f"again {i}" for i in range(10)])

            [match] = await service.search_transcripts("again")

            assert len(match.lines) == MATCHES_PER_CHRONICLE
            assert match.has_more
            assert len(await service.search_transcript(chronicle.id, "again")) == 10
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_chronicle_that_cannot_be_opened_is_skipped(self, tmp_path):
        db_manager, session, chronicles, service = await _workspace(tmp_path)
        try:
            await chronicles.create(
                Chronicle(title="Moved", project_path=str(tmp_path / "gone" / "project.db"))
            )
            found = await chronicles.create(Chronicle(title="Here"))
            await _add_lines(db_manager, found.id, "still searchable")

            matches = await service.search_transcripts("searchable")

            assert [match.chronicle.title for match in matches] == ["Here"]
            assert not (tmp_path / "gone").exists()
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_empty_query_searches_nothing(self, tmp_path):
        db_manager, session, chronicles, service = await _workspace(tmp_path)
        try:
            await chronicles.create(Chronicle(title="Anything"))
            assert await service.search_transcripts("  ") == []
        finally:
            await session.close()
            await db_manager.close_all()
