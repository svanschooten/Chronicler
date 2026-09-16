"""Tests for the Chronicle archive (.zip) export - the bundle format and the service."""

import io
import json
import zipfile
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Chronicle, Tag, TranscriptLine
from chronicler.core.project_database import DBSpeaker
from chronicler.core.services.bundle import BundleManifest, format_bundle
from chronicler.core.services.transcript_service import TranscriptService
from chronicler.core.sqlite import SQLiteChronicleRepository, SQLiteTranscriptRepository


def _manifest(**overrides) -> BundleManifest:
    base = BundleManifest(
        title="Some Chronicle",
        kind="Session",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        duration="01:30:00",
        speakers_count=3,
    )
    return base.model_copy(update=overrides)


def _opened(archive: bytearray) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(bytes(archive)))


class TestBundleFormat:
    def test_everything_sits_under_one_named_folder(self, tmp_path):
        project_db = tmp_path / "project.db"
        project_db.write_bytes(b"SQLite format 3\x00")

        archive = format_bundle(project_db, _manifest(), root="Some Chronicle")

        with _opened(archive) as bundle:
            assert sorted(bundle.namelist()) == [
                "Some Chronicle/chronicle.json",
                "Some Chronicle/project.db",
            ]

    def test_the_database_arrives_byte_for_byte(self, tmp_path):
        project_db = tmp_path / "project.db"
        project_db.write_bytes(b"SQLite format 3\x00\xff\xfe binary")

        archive = format_bundle(project_db, _manifest(), root="C")

        with _opened(archive) as bundle:
            assert bundle.read("C/project.db") == b"SQLite format 3\x00\xff\xfe binary"

    def test_the_manifest_carries_what_the_project_database_does_not(self, tmp_path):
        project_db = tmp_path / "project.db"
        project_db.write_bytes(b"db")

        archive = format_bundle(
            project_db,
            _manifest(
                title="D&D night",
                description="The one with the bridge",
                tags=["campaign", "session-3"],
            ),
            root="C",
        )

        with _opened(archive) as bundle:
            manifest = json.loads(bundle.read("C/chronicle.json"))

        assert manifest["title"] == "D&D night"
        assert manifest["description"] == "The one with the bridge"
        assert manifest["kind"] == "Session"
        assert manifest["tags"] == ["campaign", "session-3"]
        assert manifest["created_at"] == "2026-01-02T03:04:05"
        assert manifest["chronicler_version"]
        assert manifest["exported_at"]

    def test_audio_is_listed_but_not_carried_by_default(self, tmp_path):
        project_db = tmp_path / "project.db"
        project_db.write_bytes(b"db")

        archive = format_bundle(
            project_db,
            _manifest(sources=["alice.wav", "bob.wav"]),
            root="C",
        )

        with _opened(archive) as bundle:
            manifest = json.loads(bundle.read("C/chronicle.json"))
            assert not any(name.startswith("C/sources/") for name in bundle.namelist())

        assert manifest["sources"] == ["alice.wav", "bob.wav"]
        assert manifest["sources_included"] is False

    def test_audio_is_carried_when_asked_for(self, tmp_path):
        project_db = tmp_path / "project.db"
        project_db.write_bytes(b"db")
        alice = tmp_path / "alice.wav"
        alice.write_bytes(b"RIFF\x00\x00")

        archive = format_bundle(
            project_db,
            _manifest(sources=["alice.wav"], sources_included=True),
            root="C",
            sources=[alice],
        )

        with _opened(archive) as bundle:
            assert bundle.read("C/sources/alice.wav") == b"RIFF\x00\x00"
            assert json.loads(bundle.read("C/chronicle.json"))["sources_included"] is True

    def test_the_archive_is_readable_by_a_plain_zip_reader(self, tmp_path):
        project_db = tmp_path / "project.db"
        project_db.write_bytes(b"db" * 5000)

        archive = format_bundle(project_db, _manifest(), root="C")

        with _opened(archive) as bundle:
            assert bundle.testzip() is None


async def _chronicle_with_a_transcript(db_manager: DatabaseManager, **fields) -> Chronicle:
    async with db_manager.get_archive_session() as session:
        chronicle = await SQLiteChronicleRepository(session).create(
            Chronicle(title=fields.pop("title", "Some Chronicle"), **fields)
        )

    async with await db_manager.get_project_session(str(chronicle.id)) as session:
        repo = SQLiteTranscriptRepository(session)
        speaker = await repo.get_or_create_speaker("Maldal")
        await repo.add_lines(
            [
                TranscriptLine(
                    speaker_id=speaker.id,
                    speaker_name="Maldal",
                    text="We left one at least.",
                    start_time=0.0,
                    end_time=2.0,
                )
            ]
        )
        await session.commit()

    return chronicle


class TestExportZip:
    @pytest.mark.asyncio
    async def test_the_exported_database_can_be_read_back(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        chronicle = await _chronicle_with_a_transcript(db_manager)
        async with db_manager.get_archive_session() as session:
            service = TranscriptService(db_manager, SQLiteChronicleRepository(session))

            archive = await service.export_zip(chronicle.id)

        with _opened(archive) as bundle:
            (tmp_path / "unpacked").mkdir()
            bundle.extractall(tmp_path / "unpacked")

        unpacked = tmp_path / "unpacked" / "Some Chronicle" / "project.db"
        assert unpacked.exists()

        reopened = DatabaseManager(tmp_path / "reader")
        async with await reopened.get_project_session("read", custom_path=unpacked) as session:
            names = (await session.execute(select(DBSpeaker.name))).scalars().all()
        assert list(names) == ["Maldal"]

        await reopened.close_all()
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_manifest_describes_the_chronicle(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        chronicle = await _chronicle_with_a_transcript(
            db_manager,
            title="D&D night",
            description="The one with the bridge",
            kind="Session",
        )
        async with db_manager.get_archive_session() as session:
            service = TranscriptService(db_manager, SQLiteChronicleRepository(session))

            archive = await service.export_zip(chronicle.id)

        with _opened(archive) as bundle:
            manifest = json.loads(bundle.read("D_D night/chronicle.json"))

        assert manifest["title"] == "D&D night"
        assert manifest["description"] == "The one with the bridge"
        assert manifest["sources_included"] is False

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_audio_is_left_out_unless_asked_for(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        chronicle = await _chronicle_with_a_transcript(db_manager)
        sources = db_manager.get_chronicle_sources_path(str(chronicle.id))
        (sources / "alice.wav").write_bytes(b"RIFF" + b"\x00" * 2048)
        (sources / "alice.normalized.wav").write_bytes(b"RIFF" + b"\x00" * 2048)

        async with db_manager.get_archive_session() as session:
            service = TranscriptService(db_manager, SQLiteChronicleRepository(session))

            without = await service.export_zip(chronicle.id)
            with_audio = await service.export_zip(chronicle.id, include_sources=True)

        with _opened(without) as bundle:
            assert not any("sources/" in name for name in bundle.namelist())
            assert json.loads(bundle.read("Some Chronicle/chronicle.json"))["sources"] == [
                "alice.wav"
            ]

        with _opened(with_audio) as bundle:
            assert bundle.read("Some Chronicle/sources/alice.wav").startswith(b"RIFF")
            assert "Some Chronicle/sources/alice.normalized.wav" not in bundle.namelist()

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_title_that_is_not_a_safe_folder_name_is_reduced_to_one(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        chronicle = await _chronicle_with_a_transcript(db_manager, title="D&D: Session #3 / Recap")
        async with db_manager.get_archive_session() as session:
            service = TranscriptService(db_manager, SQLiteChronicleRepository(session))

            archive = await service.export_zip(chronicle.id)

        with _opened(archive) as bundle:
            roots = {name.split("/")[0] for name in bundle.namelist()}

        assert roots == {"D_D_ Session _3 _ Recap"}

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_chronicle_is_still_usable_after_being_exported(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        chronicle = await _chronicle_with_a_transcript(db_manager)
        async with db_manager.get_archive_session() as session:
            service = TranscriptService(db_manager, SQLiteChronicleRepository(session))

            await service.export_zip(chronicle.id)
            lines = await service.get_transcript(chronicle.id)

        assert [line.text for line in lines] == ["We left one at least."]

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_unknown_chronicle_is_refused(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        async with db_manager.get_archive_session() as session:
            service = TranscriptService(db_manager, SQLiteChronicleRepository(session))

            with pytest.raises(LookupError):
                await service.export_zip(uuid4())

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_tags_survive_into_the_manifest(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        chronicle = await _chronicle_with_a_transcript(db_manager)
        chronicle.tags = [Tag(name="campaign")]

        archive = format_bundle(
            (tmp_path / "chronicles" / str(chronicle.id) / "project.db"),
            BundleManifest.of(chronicle, sources=[], sources_included=False),
            root="C",
        )

        with _opened(archive) as bundle:
            assert json.loads(bundle.read("C/chronicle.json"))["tags"] == ["campaign"]

        await db_manager.close_all()
