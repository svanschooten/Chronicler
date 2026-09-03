from datetime import datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.models import AudioSource, SourceState
from chronicler.core.project_database import DBAudioSource
from chronicler.core.repositories import AudioSourceRepository


class SQLiteAudioSourceRepository(AudioSourceRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _row(self, filename: str) -> DBAudioSource | None:
        result = await self.session.execute(
            select(DBAudioSource).where(DBAudioSource.filename == filename)
        )
        return result.scalar_one_or_none()

    async def _require(self, filename: str) -> DBAudioSource:
        row = await self._row(filename)
        if row is None:
            raise KeyError(f"No audio source registered for {filename!r}")
        return row

    @staticmethod
    def _to_model(row: DBAudioSource) -> AudioSource:
        source = AudioSource.model_validate(row)
        if row.speaker:
            source.speaker_name = row.speaker.name
        return source

    async def list_sources(self) -> list[AudioSource]:
        result = await self.session.execute(select(DBAudioSource).order_by(DBAudioSource.filename))
        return [self._to_model(row) for row in result.scalars().all()]

    async def get_by_filename(self, filename: str) -> AudioSource | None:
        row = await self._row(filename)
        return self._to_model(row) if row else None

    async def register(
        self,
        filename: str,
        content_hash: str | None = None,
        size_bytes: int | None = None,
        duration_seconds: float | None = None,
    ) -> AudioSource:
        row = await self._row(filename)
        if row is None:
            row = DBAudioSource(filename=filename, added_at=datetime.now())
            self.session.add(row)

        row.content_hash = content_hash
        if size_bytes is not None:
            row.size_bytes = size_bytes
        if duration_seconds is not None:
            row.duration_seconds = duration_seconds

        await self.session.flush()
        await self.session.refresh(row)
        return self._to_model(row)

    async def set_speaker(self, filename: str, speaker_id: UUID | None) -> None:
        row = await self._require(filename)
        row.speaker_id = str(speaker_id) if speaker_id else None
        await self.session.flush()

    async def mark_transcribing(self, filename: str) -> None:
        row = await self._require(filename)
        row.transcription_state = SourceState.RUNNING.value
        row.transcription_error = None
        await self.session.flush()

    async def mark_transcribed(
        self, filename: str, content_hash: str | None, language: str | None, model: str | None
    ) -> None:
        row = await self._require(filename)
        row.transcription_state = SourceState.DONE.value
        row.transcription_error = None
        row.transcribed_at = datetime.now()
        row.transcribed_hash = content_hash
        row.transcription_language = language
        row.transcription_model = model
        await self.session.flush()

    async def mark_transcription_failed(self, filename: str, error: str) -> None:
        row = await self._require(filename)
        row.transcription_state = SourceState.FAILED.value
        row.transcription_error = error
        await self.session.flush()

    async def mark_normalizing(self, filename: str) -> None:
        row = await self._require(filename)
        row.normalization_state = SourceState.RUNNING.value
        row.normalization_error = None
        await self.session.flush()

    async def mark_normalized(
        self,
        filename: str,
        content_hash: str | None,
        normalized_filename: str,
        loudness_before: float | None = None,
        loudness_after: float | None = None,
    ) -> None:
        row = await self._require(filename)
        row.normalization_state = SourceState.DONE.value
        row.normalization_error = None
        row.normalized_at = datetime.now()
        row.normalized_hash = content_hash
        row.normalized_filename = normalized_filename
        row.loudness_before = loudness_before
        row.loudness_after = loudness_after
        await self.session.flush()

    async def mark_normalization_failed(self, filename: str, error: str) -> None:
        row = await self._require(filename)
        row.normalization_state = SourceState.FAILED.value
        row.normalization_error = error
        await self.session.flush()

    async def delete(self, filename: str) -> None:
        await self.session.execute(
            sa_delete(DBAudioSource).where(DBAudioSource.filename == filename)
        )
