import logging
from pathlib import Path
from uuid import UUID

from chronicler.core.audio_files import is_audio_track
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import AudioSource, SourceState
from chronicler.core.processing.fingerprint import fingerprint_file
from chronicler.core.processing.normalizer import NORMALIZED_SUFFIX
from chronicler.core.rpc import service
from chronicler.core.services.speakers import remember_speaker
from chronicler.core.sqlite import (
    SQLiteAudioSourceRepository,
    SQLiteKnownSpeakerRepository,
    SQLiteTranscriptRepository,
)

logger = logging.getLogger(__name__)


@service(expose=["assign_speaker", "list_audio_sources"])
class SourceService:
    """A chronicle's audio tracks: what is on disk, and which speaker each belongs to."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        known_speakers: SQLiteKnownSpeakerRepository | None = None,
    ):
        self.db_manager = db_manager
        self.known_speakers = known_speakers

    async def sources_dir(self, chronicle_id: UUID) -> Path:
        """Beside a linked project.db, otherwise in the workspace - see docs/audio-sources.md."""
        return self.db_manager.sources_path_for(
            str(chronicle_id), await self.db_manager.project_path_for(chronicle_id)
        )

    async def source_path(self, chronicle_id: UUID, filename: str) -> Path:
        return (await self.sources_dir(chronicle_id)) / filename

    async def chronicle_directory(self, chronicle_id: UUID) -> str:
        """
        Where this chronicle's files live, so a local client can offer to open it. Not
        exposed over RPC: on a thin client the path would be the server's.
        """
        project_path = await self.db_manager.project_path_for(chronicle_id)
        if project_path:
            return str(project_path.parent)
        return str(self.db_manager.workspace_path / "chronicles" / str(chronicle_id))

    async def _source_files(self, chronicle_id: UUID) -> list[Path]:
        directory = await self.sources_dir(chronicle_id)
        return list(directory.iterdir()) if directory.is_dir() else []

    async def on_disk(self, chronicle_id: UUID) -> list[Path]:
        """The audio tracks in the chronicle's sources folder, not their normalized copies."""
        return sorted(
            path
            for path in await self._source_files(chronicle_id)
            if path.is_file()
            and is_audio_track(path.name)
            and not path.name.endswith(NORMALIZED_SUFFIX)
        )

    async def list_audio_sources(self, chronicle_id: UUID) -> list[AudioSource]:
        """
        This chronicle's tracks, reconciling what is on disk with the recorded state.

        Only audio files are tracks. A row for any other file, registered before that rule,
        is dropped unless it was transcribed: then its lines name it, so it stays, and reads
        as missing only when the file itself is gone.
        """
        files = await self._source_files(chronicle_id)
        present = {path.name for path in files if path.is_file()}
        async with self.db_manager.transaction(chronicle_id) as session:
            repo = SQLiteAudioSourceRepository(session)
            for path in await self.on_disk(chronicle_id):
                await repo.register(
                    path.name,
                    content_hash=fingerprint_file(path),
                    size_bytes=path.stat().st_size,
                )
            sources = []
            for source in await repo.list_sources():
                if (
                    not is_audio_track(source.filename)
                    and source.transcription_state != SourceState.DONE
                ):
                    await repo.delete(source.filename)
                    continue
                sources.append(source)

        for source in sources:
            source.missing = source.filename not in present
            source.path = str(await self.source_path(chronicle_id, source.filename))
        return sources

    async def assign_speaker(
        self, chronicle_id: UUID, filename: str, speaker_name: str | None
    ) -> AudioSource | None:
        """Remembers which speaker a track belongs to, creating the speaker if needed."""
        async with self.db_manager.transaction(chronicle_id) as session:
            transcripts = SQLiteTranscriptRepository(session)
            sources = SQLiteAudioSourceRepository(session)
            speaker_id = None
            if speaker_name:
                speaker_id = (await transcripts.get_or_create_speaker(speaker_name)).id
            await sources.set_speaker(filename, speaker_id)
            source = await sources.get_by_filename(filename)

        if speaker_name:
            await remember_speaker(self.known_speakers, speaker_name)
        return source
