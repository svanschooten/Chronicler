"""The SUMMARIZE task handler - generate one numbered summary of a chronicle."""

import logging
from datetime import datetime

from pydantic import ValidationError

from chronicler.core.config_sections import SummarySettings
from chronicler.core.llm.client import LlmError, build_client
from chronicler.core.models import Summary, Task
from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.processing.summarizer import summarize_transcript
from chronicler.core.sqlite import SQLiteSummaryRepository, SQLiteTranscriptRepository

logger = logging.getLogger(__name__)


class SummarizeHandler(HandlerBase):
    def summary_settings(self, task: Task) -> SummarySettings:
        """The task's own prompt overrides where present, otherwise the configured defaults."""
        override = self.task_data(task).get("summary")
        if not override:
            return self.settings.summary
        merged = {**self.settings.summary.model_dump(), **override}
        try:
            return SummarySettings(**merged)
        except ValidationError as error:
            raise ValueError(f"Invalid summary configuration on task {task.id}: {error}") from error

    async def handle_summarize(self, task: Task, update_progress: ProgressCallback):
        chronicle_id = self.require_chronicle_id(task)
        data = self.task_data(task)
        settings = self.summary_settings(task)
        model = data.get("model") or self.settings.llm.model

        session = await self.project_session(chronicle_id)
        async with session:
            lines = await SQLiteTranscriptRepository(session).get_lines()

        if not lines:
            raise ValueError("This chronicle has no transcript to summarize")

        logger.info(
            f"Summarizing chronicle {chronicle_id} ({len(lines)} lines) "
            f"with {model or self.settings.llm.provider}"
        )
        await update_progress(20)

        try:
            client = build_client(self.settings.llm)
            draft = await summarize_transcript(
                client,
                lines,
                settings,
                context_window=self.settings.llm.context_window,
                model=model,
                language=settings.language or self.settings.transcription.language,
            )
        except LlmError as error:
            raise RuntimeError(f"Summarization failed: {error}") from error

        await update_progress(80)

        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteSummaryRepository(session)
            try:
                number = await repo.next_number()
                summary = await repo.add(
                    Summary(
                        number=number,
                        title=data.get("title") or f"Summary {number}",
                        content=draft.content,
                        model=draft.model,
                        provider=self.settings.llm.provider,
                        prompt_template=settings.recap_prompt,
                        language=settings.language,
                        created_at=datetime.now(),
                        chunk_count=draft.chunk_count,
                        prompt_tokens=draft.prompt_tokens,
                        completion_tokens=draft.completion_tokens,
                    )
                )
                await session.commit()
                total = await repo.count()
            except Exception:
                await session.rollback()
                raise

        await self._mark_summarized(chronicle_id, total)
        await update_progress(100)
        logger.info(
            f"Summary {summary.number} written for chronicle {chronicle_id} "
            f"({len(draft.content)} characters from {draft.chunk_count} chunk(s))"
        )
        return summary

    async def _mark_summarized(self, chronicle_id, total: int) -> None:
        if not self.chronicle_repo:
            return
        chronicle = await self.chronicle_repo.get_by_id(chronicle_id)
        if chronicle and chronicle.status in ("Imported", "Transcribed", "Cleaned"):
            chronicle.status = "Summarized"
            await self.chronicle_repo.update(chronicle)
        await self.chronicle_repo.add_tag(chronicle_id, "Summarized")
        logger.debug(f"Chronicle {chronicle_id} now has {total} summaries")
