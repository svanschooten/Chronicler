"""The NORMALIZE task handler - level one audio source into a sibling file."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from chronicler.core.models import AudioSource, Task
from chronicler.core.processing.fingerprint import fingerprint_file
from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.sqlite import SQLiteAudioSourceRepository

logger = logging.getLogger(__name__)


class NormalizeHandler(HandlerBase):
    async def handle_normalize(self, task: Task, update_progress: ProgressCallback):
        chronicle_id = self.require_chronicle_id(task)
        data = self.task_data(task)
        file_path = self.require_field(data, "file_path", "normalize")
        resolved = self.confine_to(
            file_path,
            await self.sources_root_for(chronicle_id),
            "the chronicle's sources directory",
        )

        await update_progress(10)
        result = await self.ensure_normalized(chronicle_id, resolved, force=bool(data.get("force")))
        await update_progress(100)

        if result is None:
            logger.info(f"{resolved.name} is already normalized; nothing to do")
        return result

    async def ensure_normalized(
        self, chronicle_id: UUID, source: Path, force: bool = False
    ) -> Path | None:
        """
        Normalizes `source` unless a current normalized copy already exists.

        Returns the normalized file's path when this call produced one, and None when the
        work was skipped - so a caller can tell a fresh run from a no-op.
        """
        from chronicler.core.processing import normalizer

        record = await self._source_record(chronicle_id, source)
        if not force and record is not None and record.is_normalized:
            existing = source.parent / str(record.normalized_filename)
            if existing.exists():
                return None

        await self._mark_running(chronicle_id, source)
        try:
            result = await asyncio.to_thread(
                normalizer.normalize_audio, source, self.settings.normalization
            )
        except Exception as error:
            await self._mark_failed(chronicle_id, source.name, str(error))
            raise

        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteAudioSourceRepository(session)
            await repo.mark_normalized(
                source.name,
                content_hash=fingerprint_file(source),
                normalized_filename=result.output_path.name,
                loudness_before=result.loudness_before,
                loudness_after=result.loudness_after,
            )
            await session.commit()
        return result.output_path

    async def transcription_source(self, chronicle_id: UUID, source: Path) -> Path:
        """The normalized copy of `source` when there is a current one, else `source`."""
        record = await self._source_record(chronicle_id, source)
        if record is None or not record.is_normalized or not record.normalized_filename:
            return source
        normalized = source.parent / record.normalized_filename
        return normalized if normalized.exists() else source

    async def _source_record(self, chronicle_id: UUID, source: Path) -> AudioSource | None:
        session = await self.project_session(chronicle_id)
        async with session:
            repo = SQLiteAudioSourceRepository(session)
            await repo.register(
                source.name,
                content_hash=fingerprint_file(source) if source.exists() else None,
                size_bytes=source.stat().st_size if source.exists() else None,
            )
            await session.commit()
            return await repo.get_by_filename(source.name)

    async def _mark_running(self, chronicle_id: UUID, source: Path) -> None:
        session = await self.project_session(chronicle_id)
        async with session:
            await SQLiteAudioSourceRepository(session).mark_normalizing(source.name)
            await session.commit()

    async def _mark_failed(self, chronicle_id: UUID, filename: str, error: str) -> None:
        session = await self.project_session(chronicle_id)
        async with session:
            try:
                await SQLiteAudioSourceRepository(session).mark_normalization_failed(
                    filename, error
                )
                await session.commit()
            except KeyError:
                await session.rollback()
