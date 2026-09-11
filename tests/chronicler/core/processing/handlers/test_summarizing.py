"""Tests for the SUMMARIZE task handler."""

import json
from unittest.mock import patch

import httpx
import pytest

from chronicler.core.config import Settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Task, TaskType, TranscriptLine
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteSummaryRepository,
    SQLiteTranscriptRepository,
)


@pytest.fixture(autouse=True)
def _defaults_not_the_developers_config(isolated_config):
    """
    `Settings()` here has to mean the shipped defaults.

    Without this it reads whatever is in ~/.config/Chronicler, so a machine with a real
    language model configured ran these against it - one of them over the network. See
    docs/testing.md.
    """


async def _noop_progress(_progress: int) -> None:
    pass


def _settings(**llm):
    settings = Settings()
    settings.llm.provider = "openai_compatible"
    settings.llm.base_url = "http://model:8080/v1"
    settings.llm.model = llm.get("model", "qwen3")
    return settings


def _stub_model(reply="A recap of the session."):
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "model": "qwen3",
                "choices": [{"message": {"content": reply}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _chronicle_with_transcript(db_manager, lines=3):
    session = db_manager.get_archive_session()
    async with session:
        chronicle = await SQLiteChronicleRepository(session).create(Chronicle(title="Session"))
        await session.commit()

    project = await db_manager.get_project_session(str(chronicle.id))
    async with project:
        repo = SQLiteTranscriptRepository(project)
        speaker = await repo.get_or_create_speaker("GM")
        await repo.add_lines(
            [
                TranscriptLine(
                    speaker_id=speaker.id,
                    speaker_name="GM",
                    text=f"Line {index}",
                    start_time=float(index),
                    end_time=float(index + 1),
                )
                for index in range(lines)
            ]
        )
        await project.commit()
    return chronicle


async def _summaries(db_manager, chronicle_id):
    session = await db_manager.get_project_session(str(chronicle_id))
    async with session:
        return await SQLiteSummaryRepository(session).list_summaries()


class TestHandleSummarize:
    @pytest.mark.asyncio
    async def test_writes_a_numbered_summary(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            chronicle = await _chronicle_with_transcript(db_manager)
            handlers = WorkerHandlers(db_manager, settings=_settings())

            with patch(
                "chronicler.core.llm.client.OpenAiCompatibleClient._request",
                return_value={
                    "model": "qwen3",
                    "choices": [{"message": {"content": "A recap."}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8},
                },
            ):
                await handlers.handle_summarize(
                    Task(type=TaskType.SUMMARIZE, chronicle_id=chronicle.id, data="{}"),
                    _noop_progress,
                )

            summaries = await _summaries(db_manager, chronicle.id)
            assert len(summaries) == 1
            assert summaries[0].number == 1
            assert summaries[0].content == "A recap."
            assert summaries[0].model == "qwen3"
            assert summaries[0].provider == "openai_compatible"
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_second_run_is_numbered_two(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            chronicle = await _chronicle_with_transcript(db_manager)
            handlers = WorkerHandlers(db_manager, settings=_settings())
            task = Task(type=TaskType.SUMMARIZE, chronicle_id=chronicle.id, data="{}")

            with patch(
                "chronicler.core.llm.client.OpenAiCompatibleClient._request",
                return_value={"choices": [{"message": {"content": "x"}}]},
            ):
                await handlers.handle_summarize(task, _noop_progress)
                await handlers.handle_summarize(task, _noop_progress)

            assert [s.number for s in await _summaries(db_manager, chronicle.id)] == [1, 2]
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_per_task_model_and_prompt_are_recorded(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            chronicle = await _chronicle_with_transcript(db_manager)
            handlers = WorkerHandlers(db_manager, settings=_settings())
            task = Task(
                type=TaskType.SUMMARIZE,
                chronicle_id=chronicle.id,
                data=json.dumps(
                    {
                        "model": "llama3",
                        "title": "Terse version",
                        "summary": {"recap_prompt": "Be extremely terse."},
                    }
                ),
            )

            captured = {}

            async def fake_request(self, method, path, **kwargs):
                captured.update(kwargs.get("json") or {})
                return {"choices": [{"message": {"content": "terse"}}]}

            with patch(
                "chronicler.core.llm.client.OpenAiCompatibleClient._request", new=fake_request
            ):
                await handlers.handle_summarize(task, _noop_progress)

            (summary,) = await _summaries(db_manager, chronicle.id)
            assert summary.title == "Terse version"
            assert summary.prompt_template == "Be extremely terse."
            assert captured["model"] == "llama3"
            assert captured["messages"][-1]["content"].startswith("Be extremely terse.")
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_chronicle_is_marked_summarized(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        session = db_manager.get_archive_session()
        try:
            chronicle = await _chronicle_with_transcript(db_manager)
            repo = SQLiteChronicleRepository(session)
            handlers = WorkerHandlers(db_manager, chronicle_repo=repo, settings=_settings())

            with patch(
                "chronicler.core.llm.client.OpenAiCompatibleClient._request",
                return_value={"choices": [{"message": {"content": "x"}}]},
            ):
                await handlers.handle_summarize(
                    Task(type=TaskType.SUMMARIZE, chronicle_id=chronicle.id, data="{}"),
                    _noop_progress,
                )

            updated = await repo.get_by_id(chronicle.id)
            assert updated.status == "Summarized"
            assert any(tag.name == "Summarized" for tag in updated.tags)
        finally:
            await session.close()
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_empty_transcript_is_refused(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            session = db_manager.get_archive_session()
            async with session:
                chronicle = await SQLiteChronicleRepository(session).create(
                    Chronicle(title="Empty")
                )
                await session.commit()
            handlers = WorkerHandlers(db_manager, settings=_settings())

            with pytest.raises(ValueError, match="no transcript"):
                await handlers.handle_summarize(
                    Task(type=TaskType.SUMMARIZE, chronicle_id=chronicle.id, data="{}"),
                    _noop_progress,
                )
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_unconfigured_provider_fails_clearly(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            chronicle = await _chronicle_with_transcript(db_manager)
            handlers = WorkerHandlers(db_manager, settings=Settings())

            with pytest.raises(RuntimeError, match="provider"):
                await handlers.handle_summarize(
                    Task(type=TaskType.SUMMARIZE, chronicle_id=chronicle.id, data="{}"),
                    _noop_progress,
                )
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_summaries_are_readable_through_the_service(self, tmp_path):
        from chronicler.core.services.transcript_service import TranscriptService

        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        session = db_manager.get_archive_session()
        try:
            chronicle = await _chronicle_with_transcript(db_manager)
            repo = SQLiteChronicleRepository(session)
            handlers = WorkerHandlers(db_manager, chronicle_repo=repo, settings=_settings())

            with patch(
                "chronicler.core.llm.client.OpenAiCompatibleClient._request",
                return_value={"choices": [{"message": {"content": "readable recap"}}]},
            ):
                await handlers.handle_summarize(
                    Task(type=TaskType.SUMMARIZE, chronicle_id=chronicle.id, data="{}"),
                    _noop_progress,
                )

            service = TranscriptService(db_manager, repo)
            summaries = await service.list_summaries(chronicle.id)
            assert summaries[0].content == "readable recap"

            assert summaries[0].number == 1

            text = await service.read_transcript_text(chronicle.id)
            assert "Line 0" in text

            await service.delete_summary(chronicle.id, summaries[0].id)
            assert await service.list_summaries(chronicle.id) == []
        finally:
            await session.close()
            await db_manager.close_all()
