from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from chronicler.core.database_manager import LinkRefusedError
from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.services.chronicle_service import (
    ChronicleService,
    LinkPolicy,
    remove_directory,
)


def _db_manager(workspace_path):
    """A DatabaseManager stand-in whose close_project can be awaited."""
    db_manager = MagicMock(workspace_path=workspace_path)
    db_manager.close_project = AsyncMock()
    return db_manager


def _plain_repo():
    """A repository for a chronicle with no external project path."""
    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(return_value=None)
    return repo


@pytest.mark.asyncio
async def test_list_chronicles():
    repo = MagicMock(spec=ChronicleRepository)
    repo.get_all = AsyncMock(return_value=[])

    service = ChronicleService(repo, MagicMock())
    result = await service.list_chronicles()

    assert result == []
    repo.get_all.assert_called_once()


@pytest.mark.asyncio
async def test_create_chronicle():
    repo = MagicMock(spec=ChronicleRepository)
    repo.create = AsyncMock(side_effect=lambda x: x)

    service = ChronicleService(repo, MagicMock())
    result = await service.create_chronicle("New Chronicle")

    assert result.title == "New Chronicle"
    repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_search_chronicles():
    repo = MagicMock(spec=ChronicleRepository)
    repo.search = AsyncMock(return_value=[])

    service = ChronicleService(repo, MagicMock())
    await service.search_chronicles("test")

    repo.search.assert_called_once_with("test")


@pytest.mark.asyncio
async def test_delete_chronicle_removes_directory_for_non_linked_chronicle(tmp_path):
    chronicle_id = uuid4()
    chronicle_dir = tmp_path / "chronicles" / str(chronicle_id)
    chronicle_dir.mkdir(parents=True)
    (chronicle_dir / "project.db").write_text("data")

    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(return_value=Chronicle(id=chronicle_id, title="Local"))
    repo.delete = AsyncMock()
    db_manager = _db_manager(tmp_path)

    service = ChronicleService(repo, db_manager)
    await service.delete_chronicle(chronicle_id)

    repo.delete.assert_awaited_once_with(chronicle_id)
    assert not chronicle_dir.exists()


@pytest.mark.asyncio
async def test_delete_chronicle_does_not_touch_directory_for_linked_chronicle(tmp_path):
    """
    A linked chronicle's project.db lives wherever the user pointed it - outside the
    workspace, on purpose.
    """
    chronicle_id = uuid4()
    external_dir = tmp_path / "elsewhere"
    external_dir.mkdir()
    (external_dir / "project.db").write_text("data")

    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(
        return_value=Chronicle(
            id=chronicle_id, title="Linked", project_path=str(external_dir / "project.db")
        )
    )
    repo.delete = AsyncMock()
    db_manager = _db_manager(tmp_path)

    service = ChronicleService(repo, db_manager)
    await service.delete_chronicle(chronicle_id)

    assert external_dir.exists()
    assert (external_dir / "project.db").exists()


@pytest.mark.asyncio
async def test_delete_chronicle_closes_the_project_database_before_removing_it(tmp_path):
    """
    Windows will not delete a file anything still has open - see docs/storage.md. The row
    goes before the close, so a concurrent lookup cannot cache it again afterwards.
    """
    chronicle_id = uuid4()
    chronicle_dir = tmp_path / "chronicles" / str(chronicle_id)
    chronicle_dir.mkdir(parents=True)
    (chronicle_dir / "project.db").write_text("data")

    order = []
    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(return_value=Chronicle(id=chronicle_id, title="Local"))
    repo.delete = AsyncMock(side_effect=lambda _id: order.append("deleted"))
    db_manager = _db_manager(tmp_path)
    db_manager.close_project = AsyncMock(side_effect=lambda _id: order.append("closed"))

    with patch(
        "chronicler.core.services.chronicle_service.shutil.rmtree",
        side_effect=lambda path: order.append("removed"),
    ):
        await ChronicleService(repo, db_manager).delete_chronicle(chronicle_id)

    db_manager.close_project.assert_awaited_once_with(str(chronicle_id))
    assert order == ["deleted", "closed", "removed"]


@pytest.mark.asyncio
async def test_delete_chronicle_closes_a_linked_project_database_too(tmp_path):
    """The file stays, but Chronicler must not keep holding it open."""
    chronicle_id = uuid4()
    external_dir = tmp_path / "elsewhere"
    external_dir.mkdir()

    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(
        return_value=Chronicle(
            id=chronicle_id, title="Linked", project_path=str(external_dir / "project.db")
        )
    )
    repo.delete = AsyncMock()
    db_manager = _db_manager(tmp_path)

    await ChronicleService(repo, db_manager).delete_chronicle(chronicle_id)

    db_manager.close_project.assert_awaited_once_with(str(chronicle_id))


def _repo_holding(chronicle: Chronicle):
    repo = MagicMock(spec=ChronicleRepository)
    repo.get_by_id = AsyncMock(return_value=chronicle)
    repo.update = AsyncMock(side_effect=lambda updated: updated)
    return repo


@pytest.mark.asyncio
async def test_an_update_cannot_move_a_chronicle(tmp_path):
    """Ticket 076: where a chronicle's database lives is set when it is created or linked."""
    chronicle = Chronicle(title="Linked", project_path=str(tmp_path / "old" / "project.db"))
    repo = _repo_holding(chronicle)
    service = ChronicleService(repo, _db_manager(tmp_path))

    moved = chronicle.model_copy(
        update={"title": "Renamed", "project_path": str(tmp_path / "new" / "project.db")}
    )
    updated = await service.update_chronicle(moved)

    assert updated.title == "Renamed"
    assert updated.project_path == chronicle.project_path


class TestLinkPolicy:
    """Ticket 076: a server confines the project paths its remote callers can name."""

    def _service(self, tmp_path, allowed):
        repo = MagicMock(spec=ChronicleRepository)
        repo.create = AsyncMock(side_effect=lambda chronicle: chronicle)
        return ChronicleService(repo, _db_manager(tmp_path), link_policy=LinkPolicy(allowed))

    def test_a_path_inside_an_allowed_folder_is_kept(self, tmp_path):
        allowed = tmp_path / "shared"

        confined = LinkPolicy([allowed]).confine(str(allowed / "a" / "project.db"))

        assert confined == (allowed / "a" / "project.db").resolve()

    @pytest.mark.parametrize("name", ["elsewhere/project.db", "shared/../elsewhere/project.db"])
    def test_a_path_outside_every_allowed_folder_is_refused(self, tmp_path, name):
        with pytest.raises(LinkRefusedError) as refused:
            LinkPolicy([tmp_path / "shared"]).confine(str(tmp_path / name))
        assert refused.value.reason == "not_allowed"

    def test_no_allowed_folders_allows_no_linked_chronicle(self, tmp_path):
        with pytest.raises(LinkRefusedError):
            LinkPolicy([]).confine(str(tmp_path / "project.db"))

    @pytest.mark.asyncio
    async def test_create_always_puts_the_database_in_the_workspace(self, tmp_path):
        service = self._service(tmp_path, [])

        assert (await service.create_chronicle("In the workspace")).project_path is None

    @pytest.mark.asyncio
    async def test_linking_outside_is_refused_before_the_file_is_read(self, tmp_path):
        service = self._service(tmp_path, [tmp_path / "shared"])

        with (
            patch("chronicler.core.services.chronicle_service.check_linkable_project") as check,
            pytest.raises(LinkRefusedError) as refused,
        ):
            await service.link_external_chronicle(str(tmp_path / "elsewhere" / "project.db"))

        assert refused.value.reason == "not_allowed"
        check.assert_not_called()

    @pytest.mark.asyncio
    async def test_without_a_policy_any_path_is_allowed(self, tmp_path):
        """The full-stack app: the caller is the machine's own user."""
        repo = MagicMock(spec=ChronicleRepository)
        repo.create = AsyncMock(side_effect=lambda chronicle: chronicle)
        service = ChronicleService(repo, _db_manager(tmp_path))

        assert LinkPolicy().confine(str(tmp_path / "x" / "project.db")) == (
            tmp_path / "x" / "project.db"
        )
        assert service.link_policy.allowed_dirs is None


@pytest.mark.asyncio
async def test_removing_a_directory_retries_before_giving_up(tmp_path):
    """A file held open for a moment is a pause on Windows, not a failed delete."""
    attempts = []

    def flaky(path):
        attempts.append(path)
        if len(attempts) < 3:
            raise OSError(32, "The process cannot access the file")

    with patch("chronicler.core.services.chronicle_service.shutil.rmtree", side_effect=flaky):
        with patch("chronicler.core.services.chronicle_service.REMOVAL_BACKOFF_SECONDS", 0):
            await remove_directory(tmp_path)

    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_removing_a_directory_gives_up_and_raises_eventually(tmp_path):
    with patch(
        "chronicler.core.services.chronicle_service.shutil.rmtree",
        side_effect=OSError(32, "The process cannot access the file"),
    ):
        with patch("chronicler.core.services.chronicle_service.REMOVAL_BACKOFF_SECONDS", 0):
            with pytest.raises(OSError):
                await remove_directory(tmp_path)


@pytest.mark.asyncio
async def test_add_audio_source_moves_file_into_durable_sources_dir(tmp_path):
    chronicle_id = uuid4()
    staged_file = tmp_path / "imports" / "a1b2c3.mp3"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(b"fake audio")

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.project_path_for = AsyncMock(return_value=None)
    db_manager.get_imports_path.return_value = tmp_path / "imports"
    db_manager.ensure_sources_path_for.return_value = (
        tmp_path / "chronicles" / str(chronicle_id) / "sources"
    )
    (tmp_path / "chronicles" / str(chronicle_id) / "sources").mkdir(parents=True)

    service = ChronicleService(_plain_repo(), db_manager)
    result = await service.add_audio_source(chronicle_id, str(staged_file), "recording.mp3")

    assert not staged_file.exists()
    dest = tmp_path / "chronicles" / str(chronicle_id) / "sources" / "recording.mp3"
    assert dest.exists()
    assert result == str(dest)


@pytest.mark.asyncio
async def test_add_audio_source_refuses_a_file_that_is_not_audio(tmp_path):
    """It would sit in sources/ and never be listed, so it is refused and the staged copy goes."""
    from chronicler.core.audio_files import UnsupportedAudioError

    chronicle_id = uuid4()
    staged_file = tmp_path / "imports" / "a1b2c3.txt"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(b"notes")
    sources = tmp_path / "chronicles" / str(chronicle_id) / "sources"
    sources.mkdir(parents=True)

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.project_path_for = AsyncMock(return_value=None)
    db_manager.get_imports_path.return_value = tmp_path / "imports"
    db_manager.ensure_sources_path_for.return_value = sources

    service = ChronicleService(_plain_repo(), db_manager)
    with pytest.raises(UnsupportedAudioError, match="notes.txt is not an audio file"):
        await service.add_audio_source(chronicle_id, str(staged_file), "notes.txt")

    assert not staged_file.exists()
    assert list(sources.iterdir()) == []


@pytest.mark.asyncio
async def test_add_audio_source_avoids_overwriting_same_name(tmp_path):
    chronicle_id = uuid4()
    sources_dir = tmp_path / "chronicles" / str(chronicle_id) / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "recording.mp3").write_bytes(b"existing track")

    staged_file = tmp_path / "imports" / "a1b2c3.mp3"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(b"new track")

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.project_path_for = AsyncMock(return_value=None)
    db_manager.get_imports_path.return_value = tmp_path / "imports"
    db_manager.ensure_sources_path_for.return_value = sources_dir

    service = ChronicleService(_plain_repo(), db_manager)
    result = await service.add_audio_source(chronicle_id, str(staged_file), "recording.mp3")

    assert result == str(sources_dir / "recording (1).mp3")
    assert (sources_dir / "recording.mp3").read_bytes() == b"existing track"
    assert (sources_dir / "recording (1).mp3").read_bytes() == b"new track"


def _service_with_workspace(tmp_path, chronicle_id):
    """
    A ChronicleService whose imports/ and sources/ directories really exist, so the path
    confinement in add_audio_source is exercised against real paths.
    """
    imports_dir = tmp_path / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    sources_dir = tmp_path / "chronicles" / str(chronicle_id) / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.project_path_for = AsyncMock(return_value=None)
    db_manager.get_imports_path.return_value = imports_dir
    db_manager.ensure_sources_path_for.return_value = sources_dir
    return ChronicleService(_plain_repo(), db_manager), imports_dir, sources_dir


@pytest.mark.asyncio
async def test_add_audio_source_rejects_file_outside_imports_dir(tmp_path):
    """add_audio_source is an @service method, so file_path arrives from an RPC caller."""
    chronicle_id = uuid4()
    service, _imports_dir, sources_dir = _service_with_workspace(tmp_path, chronicle_id)

    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("SECRET")

    with pytest.raises(ValueError, match="imports directory"):
        await service.add_audio_source(chronicle_id, str(outside))

    assert outside.read_text() == "SECRET"
    assert list(sources_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_add_audio_source_rejects_traversal_out_of_imports_dir(tmp_path):
    chronicle_id = uuid4()
    service, imports_dir, _sources_dir = _service_with_workspace(tmp_path, chronicle_id)

    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("SECRET")

    traversal = imports_dir / ".." / "outside" / "secret.txt"
    with pytest.raises(ValueError, match="imports directory"):
        await service.add_audio_source(chronicle_id, str(traversal))

    assert outside.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_name",
    [
        "../../../../pwned.wav",
        "..\\..\\pwned.wav",
        "/etc/pwned.wav",
        "..",
        "",
    ],
)
async def test_add_audio_source_keeps_hostile_original_name_inside_sources(tmp_path, hostile_name):
    """
    original_name is kept readable rather than uuid'd, so it must not be able to act as a
    path - it used to be joined onto sources_dir verbatim.
    """
    chronicle_id = uuid4()
    service, imports_dir, sources_dir = _service_with_workspace(tmp_path, chronicle_id)

    staged = imports_dir / "deadbeef.wav"
    staged.write_bytes(b"payload")

    result = Path(await service.add_audio_source(chronicle_id, str(staged), hostile_name))

    assert result.parent == sources_dir
    assert result.resolve().is_relative_to(sources_dir.resolve())
    assert result.read_bytes() == b"payload"


@pytest.mark.asyncio
async def test_add_audio_source_still_keeps_a_readable_name(tmp_path):
    chronicle_id = uuid4()
    service, imports_dir, sources_dir = _service_with_workspace(tmp_path, chronicle_id)

    staged = imports_dir / "deadbeef.wav"
    staged.write_bytes(b"payload")

    result = await service.add_audio_source(chronicle_id, str(staged), "session-3 GM.wav")

    assert result == str(sources_dir / "session-3 GM.wav")


class TestEditChronicle:
    """Ticket 075: a user edits four fields, and nothing else of the chronicle moves."""

    def _service(self, tmp_path, chronicle):
        repo = _repo_holding(chronicle)
        return ChronicleService(repo, _db_manager(tmp_path)), repo

    @pytest.mark.asyncio
    async def test_only_the_given_fields_change(self, tmp_path):
        chronicle = Chronicle(
            title="Old",
            description="Keep me",
            duration="1h 24m",
            status="Transcribed",
            speakers_count=3,
            project_path=str(tmp_path / "x" / "project.db"),
        )
        service, _ = self._service(tmp_path, chronicle)

        edited = await service.edit_chronicle(chronicle.id, title="New")

        assert edited.title == "New"
        assert (edited.description, edited.duration) == ("Keep me", "1h 24m")
        assert (edited.status, edited.speakers_count) == ("Transcribed", 3)
        assert edited.project_path == chronicle.project_path

    @pytest.mark.asyncio
    async def test_an_empty_string_clears_an_optional_field(self, tmp_path):
        chronicle = Chronicle(title="T", description="d", kind="Campaign", duration="5m")
        service, _ = self._service(tmp_path, chronicle)

        edited = await service.edit_chronicle(chronicle.id, description="", kind="", duration="")

        assert (edited.description, edited.kind, edited.duration) == (None, "Unknown", None)

    @pytest.mark.asyncio
    async def test_a_blank_title_is_ignored(self, tmp_path):
        chronicle = Chronicle(title="Kept")
        service, _ = self._service(tmp_path, chronicle)

        assert (await service.edit_chronicle(chronicle.id, title="")).title == "Kept"

    @pytest.mark.asyncio
    async def test_an_unknown_chronicle_is_refused(self, tmp_path):
        repo = MagicMock(spec=ChronicleRepository)
        repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(LookupError):
            await ChronicleService(repo, _db_manager(tmp_path)).edit_chronicle(uuid4(), title="x")


def test_the_whole_object_update_is_not_a_remote_method():
    from chronicler.core.rpc import exposed_methods

    exposed = exposed_methods(ChronicleService)

    assert "edit_chronicle" in exposed
    assert "update_chronicle" not in exposed
