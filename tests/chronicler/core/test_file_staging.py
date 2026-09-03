from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import (
    LocalFileStager,
    RemoteFileStager,
    sanitize_stage_name,
    stage_local_file,
)
from chronicler.core.local_container import register_local_repositories
from chronicler.core.rpc import RpcServer


def test_sanitize_stage_name_keeps_only_whitelisted_extension():
    name = sanitize_stage_name("my transcript.txt")
    assert name.endswith(".txt")
    assert "my transcript" not in name


def test_sanitize_stage_name_strips_traversal_and_separators():
    for evil in ("../../../etc/passwd", "..\\..\\windows\\system32\\config", "/etc/passwd"):
        name = sanitize_stage_name(evil)
        assert "/" not in name
        assert "\\" not in name
        assert ".." not in name


def test_sanitize_stage_name_handles_none_and_empty():
    assert sanitize_stage_name(None)
    assert sanitize_stage_name("")


def test_sanitize_stage_name_is_unique_per_call():
    assert sanitize_stage_name("a.txt") != sanitize_stage_name("a.txt")


def test_stage_local_file_copies_into_imports_dir(tmp_path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()
    imports_dir = tmp_path / "workspace" / "imports"
    imports_dir.mkdir(parents=True)

    source_file = source_dir / "transcript.txt"
    source_file.write_text("Alice: hello\n")

    staged = stage_local_file(source_file, imports_dir)

    assert staged.parent == imports_dir
    assert staged.name != "transcript.txt"
    assert staged.suffix == ".txt"
    assert staged.read_text() == "Alice: hello\n"
    assert source_file.exists()


def test_stage_local_file_two_files_same_name_no_collision(tmp_path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()
    imports_dir = tmp_path / "workspace" / "imports"
    imports_dir.mkdir(parents=True)

    file_a = source_dir / "transcript.txt"
    file_a.write_text("first")
    staged_a = stage_local_file(file_a, imports_dir)

    file_a.write_text("second")
    staged_b = stage_local_file(file_a, imports_dir)

    assert staged_a != staged_b
    assert staged_a.read_text() == "first"
    assert staged_b.read_text() == "second"


def test_stage_local_file_result_is_relative_to_imports_dir(tmp_path):
    source_file = tmp_path / "weird..name.txt"
    source_file.write_text("data")
    imports_dir = tmp_path / "imports"
    imports_dir.mkdir()

    staged = stage_local_file(source_file, imports_dir)

    assert Path(staged).resolve().is_relative_to(imports_dir.resolve())


@pytest.mark.asyncio
async def test_local_file_stager_copies_into_imports_dir(tmp_path):
    imports_dir = tmp_path / "imports"
    imports_dir.mkdir()
    source_file = tmp_path / "recording.mp3"
    source_file.write_text("fake audio")

    stager = LocalFileStager(imports_dir)
    staged_path = await stager.stage(str(source_file))

    assert Path(staged_path).resolve().is_relative_to(imports_dir.resolve())
    assert Path(staged_path).name != "recording.mp3"


@pytest.mark.asyncio
async def test_remote_file_stager_uploads_and_returns_server_path(tmp_path):
    """
    Same primitive as LocalFileStager (turn a local path into something safe to queue), but
    for thin-client mode: actually upload it via /upload, the same endpoint the web client's
    proxy already uses.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        container = Container()
        register_local_repositories(container, db_manager)
        upstream_app = RpcServer(container, services=[], api_key="secret-key").build()

        source_file = tmp_path / "picked" / "transcript.txt"
        source_file.parent.mkdir()
        source_file.write_text("Alice: hi\n")

        transport = ASGITransport(app=upstream_app)
        async with AsyncClient(transport=transport, base_url="http://upstream") as client:
            stager = RemoteFileStager("http://upstream", "secret-key", client=client)
            staged_path = await stager.stage(str(source_file))

        assert Path(staged_path).resolve().is_relative_to(db_manager.get_imports_path().resolve())
        assert Path(staged_path).name != "transcript.txt"
        assert Path(staged_path).read_text() == "Alice: hi\n"
    finally:
        await db_manager.close_all()
