from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from chronicler.core.models import Chronicle
from chronicler.core.repositories import ChronicleRepository
from chronicler.core.services.chronicle_service import ChronicleService


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
    db_manager = MagicMock(workspace_path=tmp_path)

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
    db_manager = MagicMock(workspace_path=tmp_path)

    service = ChronicleService(repo, db_manager)
    await service.delete_chronicle(chronicle_id)

    assert external_dir.exists()
    assert (external_dir / "project.db").exists()


@pytest.mark.asyncio
async def test_add_audio_source_moves_file_into_durable_sources_dir(tmp_path):
    chronicle_id = uuid4()
    staged_file = tmp_path / "imports" / "a1b2c3.mp3"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(b"fake audio")

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.get_imports_path.return_value = tmp_path / "imports"
    db_manager.sources_path_for.return_value = (
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
async def test_add_audio_source_avoids_overwriting_same_name(tmp_path):
    chronicle_id = uuid4()
    sources_dir = tmp_path / "chronicles" / str(chronicle_id) / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "recording.mp3").write_bytes(b"existing track")

    staged_file = tmp_path / "imports" / "a1b2c3.mp3"
    staged_file.parent.mkdir(parents=True)
    staged_file.write_bytes(b"new track")

    db_manager = MagicMock(workspace_path=tmp_path)
    db_manager.get_imports_path.return_value = tmp_path / "imports"
    db_manager.sources_path_for.return_value = sources_dir

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
    db_manager.get_imports_path.return_value = imports_dir
    db_manager.sources_path_for.return_value = sources_dir
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
