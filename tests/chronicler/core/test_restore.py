"""Undoing a clean, an overwriting import or a re-transcription from its snapshot."""

import asyncio
import json
from uuid import uuid4

import pytest
import pytest_asyncio

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.models import Task, TaskType
from chronicler.core.processing.handlers import WorkerHandlers
from chronicler.core.sqlite import SQLiteTranscriptRepository
from tests.projects import register_chronicle


@pytest.fixture(autouse=True)
def _defaults_not_the_developers_config(isolated_config):
    """Handlers read the configured settings; see the shared fixture in conftest."""


async def _noop(_progress: int) -> None:
    pass


async def _import(handlers, db_manager, chronicle_id, text, append=False):
    file = db_manager.get_imports_path() / f"{uuid4().hex}.txt"
    file.write_text(text)
    data = {"file_path": str(file)}
    if append:
        data["append"] = True
    await handlers.handle_import(
        Task(type=TaskType.IMPORT, chronicle_id=chronicle_id, data=json.dumps(data)), _noop
    )


async def _texts(db_manager, chronicle_id):
    async with await db_manager.get_project_session(str(chronicle_id)) as session:
        return [line.text for line in await SQLiteTranscriptRepository(session).get_lines()]


async def _found(db_manager, chronicle_id, query):
    async with await db_manager.get_project_session(str(chronicle_id)) as session:
        return [line.text for line in await SQLiteTranscriptRepository(session).search(query)]


@pytest_asyncio.fixture
async def workspace(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    chronicle_id = uuid4()
    await register_chronicle(db_manager, chronicle_id)
    yield db_manager, WorkerHandlers(db_manager), chronicle_id
    await db_manager.close_all()


@pytest.mark.asyncio
async def test_a_clean_can_be_undone(workspace):
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: Um\nAlice: We ride at dawn\n")
    await handlers.handle_clean(Task(type=TaskType.CLEAN, chronicle_id=chronicle_id), _noop)
    cleaned = await _texts(db_manager, chronicle_id)

    (snapshot,) = await db_manager.list_snapshots(chronicle_id)
    await db_manager.restore_project(chronicle_id, snapshot.name)

    assert snapshot.kind == "clean"
    assert await _texts(db_manager, chronicle_id) == ["Um", "We ride at dawn"]
    assert cleaned != ["Um", "We ride at dawn"]


@pytest.mark.asyncio
async def test_an_overwriting_import_can_be_undone_but_the_first_import_needs_no_copy(workspace):
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: First transcript\n")
    assert await db_manager.list_snapshots(chronicle_id) == []

    await _import(handlers, db_manager, chronicle_id, "Bob: Something else\n")
    (snapshot,) = await db_manager.list_snapshots(chronicle_id)
    await db_manager.restore_project(chronicle_id, snapshot.name)

    assert snapshot.kind == "import"
    assert await _texts(db_manager, chronicle_id) == ["First transcript"]


@pytest.mark.asyncio
async def test_appending_keeps_everything_so_it_makes_no_copy(workspace):
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: One\n")

    await _import(handlers, db_manager, chronicle_id, "Alice: Two\n", append=True)

    assert await db_manager.list_snapshots(chronicle_id) == []


@pytest.mark.asyncio
async def test_a_restore_can_itself_be_undone_and_repeated(workspace):
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: Original\n")
    await _import(handlers, db_manager, chronicle_id, "Alice: Replacement\n")
    (overwritten,) = await db_manager.list_snapshots(chronicle_id)

    await db_manager.restore_project(chronicle_id, overwritten.name)
    restores = [s for s in await db_manager.list_snapshots(chronicle_id) if s.kind == "restore"]
    await db_manager.restore_project(chronicle_id, restores[0].name)

    assert await _texts(db_manager, chronicle_id) == ["Replacement"]
    await db_manager.restore_project(chronicle_id, overwritten.name)
    assert await _texts(db_manager, chronicle_id) == ["Original"]


@pytest.mark.asyncio
async def test_search_finds_the_restored_lines_not_the_replaced_ones(workspace):
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: dragons everywhere\n")
    await _import(handlers, db_manager, chronicle_id, "Alice: only goblins here\n")
    (snapshot,) = await db_manager.list_snapshots(chronicle_id)

    await db_manager.restore_project(chronicle_id, snapshot.name)

    assert await _found(db_manager, chronicle_id, "dragons") == ["dragons everywhere"]
    assert await _found(db_manager, chronicle_id, "goblins") == []


@pytest.mark.asyncio
async def test_snapshots_are_listed_newest_first(workspace):
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: One\n")
    for _ in range(2):
        await _import(handlers, db_manager, chronicle_id, "Alice: Again\n")

    snapshots = await db_manager.list_snapshots(chronicle_id)

    assert [s.created_at for s in snapshots] == sorted(
        (s.created_at for s in snapshots), reverse=True
    )
    assert len(snapshots) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "project.db", "before-clean-someone-else-20260101-000000-000000.db"],
)
async def test_only_this_chronicles_snapshots_can_be_restored(workspace, name):
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: Kept\n")

    with pytest.raises(LookupError):
        await db_manager.restore_project(chronicle_id, name)

    assert await _texts(db_manager, chronicle_id) == ["Kept"]


@pytest.mark.asyncio
async def test_another_chronicles_snapshot_in_a_shared_folder_is_refused(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    first, second = uuid4(), uuid4()
    folder = tmp_path / "shared"
    await register_chronicle(db_manager, first, folder / "a.db")
    await register_chronicle(db_manager, second, folder / "b.db")
    handlers = WorkerHandlers(db_manager)
    try:
        await _import(handlers, db_manager, second, "Bob: Other\n")
        await _import(handlers, db_manager, first, "Alice: One\n")
        await _import(handlers, db_manager, first, "Alice: Two\n")
        (snapshot,) = await db_manager.list_snapshots(first)
        assert await db_manager.list_snapshots(second) == []

        with pytest.raises(LookupError):
            await db_manager.restore_project(second, snapshot.name)
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_panels_opening_during_a_restore_wait_and_then_see_the_restored_file(workspace):
    """The transcript view loads three panels at once; none may reopen the old file mid-swap."""
    db_manager, handlers, chronicle_id = workspace
    await _import(handlers, db_manager, chronicle_id, "Alice: Original\n")
    await _import(handlers, db_manager, chronicle_id, "Alice: Replacement\n")
    (snapshot,) = await db_manager.list_snapshots(chronicle_id)

    async def read():
        return await _texts(db_manager, chronicle_id)

    results = await asyncio.gather(
        db_manager.restore_project(chronicle_id, snapshot.name), read(), read(), read()
    )

    assert await _texts(db_manager, chronicle_id) == ["Original"]
    assert all(texts in (["Original"], ["Replacement"]) for texts in results[1:])


@pytest.mark.asyncio
async def test_restoring_through_the_service_refreshes_the_workspace_record(tmp_path):
    from chronicler.core.models import Chronicle
    from chronicler.core.services.chronicle_service import ChronicleService
    from chronicler.core.services.transcript_service import TranscriptService
    from chronicler.core.sqlite import SQLiteChronicleRepository

    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    handlers = WorkerHandlers(db_manager)
    try:
        async with db_manager.get_archive_session() as session:
            repository = SQLiteChronicleRepository(session)
            chronicle = await repository.create(Chronicle(title="Restorable"))
            service = ChronicleService(
                repository, db_manager, TranscriptService(db_manager, repository)
            )
            await _import(handlers, db_manager, chronicle.id, "Alice: One\nBob: Two\n")
            await _import(handlers, db_manager, chronicle.id, "Carol: Only me\n")
            (snapshot,) = await service.list_snapshots(chronicle.id)

            restored = await service.restore_snapshot(chronicle.id, snapshot.name)

        assert restored.speakers_count == 2
    finally:
        await db_manager.close_all()
