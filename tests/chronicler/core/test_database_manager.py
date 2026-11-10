import asyncio
import threading
import time

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from chronicler.core.database import DBChronicle
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.project_database import DBSpeaker
from chronicler.core.workspace_lock import WorkspaceLockedError
from tests.projects import forget_chronicle, register_chronicle


@pytest.mark.asyncio
async def test_database_manager_init(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()

    assert (tmp_path / "chronicler.db").exists()

    async with db_manager.get_archive_session() as session:
        result = await session.execute(select(DBChronicle))
        assert result.scalars().all() == []

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_database_manager_project_session(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    chronicle_id = "test-chronicle"

    await register_chronicle(db_manager, chronicle_id)
    async with await db_manager.get_project_session(chronicle_id) as session:
        result = await session.execute(select(DBSpeaker))
        assert result.scalars().all() == []

    assert (tmp_path / "chronicles" / chronicle_id / "project.db").exists()

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_close_project_releases_the_file_handle(tmp_path):
    """
    Windows refuses to delete a file anything still holds open - see docs/storage.md.
    """
    db_manager = DatabaseManager(tmp_path)
    chronicle_id = "held-open"

    await register_chronicle(db_manager, chronicle_id)
    async with await db_manager.get_project_session(chronicle_id) as session:
        await session.execute(select(DBSpeaker))

    assert chronicle_id in db_manager._project_engines

    await db_manager.close_project(chronicle_id)

    assert chronicle_id not in db_manager._project_engines
    assert (tmp_path / "chronicles" / chronicle_id / "project.db").exists()

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_opening_many_chronicles_leaves_the_thread_count_flat(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    for chronicle_id in ["first", *(f"chronicle-{index}" for index in range(20))]:
        await register_chronicle(db_manager, chronicle_id)
    async with await db_manager.get_project_session("first") as session:
        await session.execute(select(DBSpeaker))
    baseline = threading.active_count()

    for index in range(20):
        async with await db_manager.get_project_session(f"chronicle-{index}") as session:
            await session.execute(select(DBSpeaker))
    await asyncio.sleep(0.1)

    assert threading.active_count() <= baseline
    await db_manager.close_all()


@pytest.mark.asyncio
async def test_close_project_for_an_unopened_chronicle_is_a_noop(tmp_path):
    db_manager = DatabaseManager(tmp_path)

    await db_manager.close_project("never-opened")

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_a_closed_project_can_be_reopened(tmp_path):
    """Closing releases the file; it does not make the chronicle unusable."""
    db_manager = DatabaseManager(tmp_path)
    chronicle_id = "reopened"

    await register_chronicle(db_manager, chronicle_id)
    async with await db_manager.get_project_session(chronicle_id) as session:
        await session.execute(select(DBSpeaker))
    await db_manager.close_project(chronicle_id)

    async with await db_manager.get_project_session(chronicle_id) as session:
        assert (await session.execute(select(DBSpeaker))).scalars().all() == []

    await db_manager.close_all()


def test_get_chronicle_sources_path_creates_directory(tmp_path):
    db_manager = DatabaseManager(tmp_path)

    path = db_manager.get_chronicle_sources_path("test-chronicle")

    assert path == tmp_path / "chronicles" / "test-chronicle" / "sources"
    assert path.is_dir()


def _head_revision(chain: str) -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from chronicler.core.database_manager import _MIGRATIONS_ROOT

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / chain))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    return head


@pytest.mark.asyncio
async def test_init_archive_stamps_alembic_head(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()

    async with db_manager.get_archive_session() as session:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        assert result.scalar_one() == _head_revision("archive")

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_init_archive_twice_is_a_noop_not_an_error(tmp_path):
    """Simulates a second app launch against an already-migrated workspace."""
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    await db_manager.init_archive()

    async with db_manager.get_archive_session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM alembic_version"))
        assert result.scalar_one() == 1

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_project_session_stamps_alembic_head(tmp_path):
    db_manager = DatabaseManager(tmp_path)

    await register_chronicle(db_manager, "test-chronicle")
    session = await db_manager.get_project_session("test-chronicle")
    async with session:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        assert result.scalar_one() == _head_revision("project")

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_project_session_opened_twice_is_a_noop_not_an_error(tmp_path):
    """Simulates navigating to the same chronicle's transcript view twice."""
    db_manager = DatabaseManager(tmp_path)

    await register_chronicle(db_manager, "test-chronicle")
    session1 = await db_manager.get_project_session("test-chronicle")
    await session1.close()
    session2 = await db_manager.get_project_session("test-chronicle")

    async with session2:
        result = await session2.execute(text("SELECT COUNT(*) FROM alembic_version"))
        assert result.scalar_one() == 1

    await db_manager.close_all()


class TestConcurrentProjectSessions:
    """
    The transcript view mounts three panels that each open a project session at once, so
    engine creation has to be atomic - a check-then-populate across an await let all three
    run Alembic on the same file, producing "table already exists" and "database is
    locked".
    """

    @pytest.mark.asyncio
    async def test_concurrent_first_access_runs_migrations_once(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            sessions = await asyncio.gather(
                *(db_manager.get_project_session("chronicle-1") for _ in range(6))
            )
            for session in sessions:
                await session.close()

            assert len(db_manager._project_engines) == 1
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_concurrent_access_to_different_chronicles_is_not_serialised_wrongly(
        self, tmp_path
    ):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            sessions = await asyncio.gather(
                *(db_manager.get_project_session(f"chronicle-{index}") for index in range(4))
            )
            for session in sessions:
                await session.close()

            assert len(db_manager._project_engines) == 4
        finally:
            await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_schema_is_usable_after_a_concurrent_open(self, tmp_path):
        from chronicler.core.sqlite import SQLiteAudioSourceRepository, SQLiteSummaryRepository

        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()
        try:
            sessions = await asyncio.gather(
                *(db_manager.get_project_session("chronicle-1") for _ in range(4))
            )
            session = sessions[0]
            async with session:
                await SQLiteAudioSourceRepository(session).register("gm.wav", content_hash="h")
                assert await SQLiteSummaryRepository(session).count() == 0
                await session.commit()
            for extra in sessions[1:]:
                await extra.close()
        finally:
            await db_manager.close_all()


class TestProjectSnapshots:
    """`snapshot_project` is what makes a Chronicle archive export consistent."""

    @pytest.mark.asyncio
    async def test_snapshot_copies_the_committed_contents(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        chronicle_id = "snapshot-me"

        await register_chronicle(db_manager, chronicle_id)
        async with await db_manager.get_project_session(chronicle_id) as session:
            session.add(DBSpeaker(name="Maldal"))
            await session.commit()

        destination = tmp_path / "out" / "project.db"
        await db_manager.snapshot_project(chronicle_id, destination)

        assert destination.exists()
        copy = DatabaseManager(tmp_path / "elsewhere")
        await register_chronicle(copy, "read-back", destination)
        async with await copy.get_project_session("read-back") as session:
            names = (await session.execute(select(DBSpeaker.name))).scalars().all()
        assert list(names) == ["Maldal"]

        await copy.close_all()
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_the_live_database_still_works_after_a_snapshot(self, tmp_path):
        """A snapshot must not disturb the connection the app is still using."""
        db_manager = DatabaseManager(tmp_path)
        chronicle_id = "still-live"

        await register_chronicle(db_manager, chronicle_id)
        async with await db_manager.get_project_session(chronicle_id) as session:
            session.add(DBSpeaker(name="Before"))
            await session.commit()

        await db_manager.snapshot_project(chronicle_id, tmp_path / "out" / "project.db")

        async with await db_manager.get_project_session(chronicle_id) as session:
            session.add(DBSpeaker(name="After"))
            await session.commit()
            names = (await session.execute(select(DBSpeaker.name))).scalars().all()
        assert sorted(names) == ["After", "Before"]

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_snapshot_follows_a_linked_chronicle_to_its_own_path(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        linked = tmp_path / "elsewhere" / "project.db"
        linked.parent.mkdir(parents=True)

        await register_chronicle(db_manager, "linked", linked)
        async with await db_manager.get_project_session("linked") as session:
            session.add(DBSpeaker(name="Windrider"))
            await session.commit()

        destination = tmp_path / "out" / "project.db"
        await db_manager.snapshot_project("linked", destination)

        assert destination.exists()
        assert not (tmp_path / "chronicles" / "linked").exists()

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_snapshot_refuses_to_overwrite_an_existing_file(self, tmp_path):
        """
        SQLite's own rule, surfaced rather than swallowed: VACUUM INTO will not write over
        a file that is already there, and silently reusing a stale one would ship it.
        """
        db_manager = DatabaseManager(tmp_path)
        destination = tmp_path / "taken.db"
        destination.write_text("not a database")

        with pytest.raises(FileExistsError):
            await db_manager.snapshot_project("whatever", destination)

        assert destination.read_text() == "not a database"

        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_path_with_a_quote_in_it_is_still_snapshotted(self, tmp_path):
        """
        The destination goes into SQL as a literal, so a quote in the path has to survive
        being escaped rather than truncating the statement.
        """
        db_manager = DatabaseManager(tmp_path)

        await register_chronicle(db_manager, "quoted")
        async with await db_manager.get_project_session("quoted") as session:
            session.add(DBSpeaker(name="Sergus"))
            await session.commit()

        destination = tmp_path / "it's here" / "project.db"
        await db_manager.snapshot_project("quoted", destination)

        assert destination.exists()

        await db_manager.close_all()


@pytest.mark.asyncio
async def test_a_second_writer_fails_fast_while_the_first_holds_the_lock(two_sessions):
    two_sessions.first.add(DBChronicle(title="held"))
    await two_sessions.first.flush()

    two_sessions.second.add(DBChronicle(title="blocked"))
    started = time.monotonic()
    with pytest.raises(OperationalError, match="database is locked"):
        await two_sessions.second.flush()

    assert time.monotonic() - started < 1.0
    await two_sessions.second.rollback()

    await two_sessions.first.commit()
    titles = (await two_sessions.second.execute(select(DBChronicle.title))).scalars().all()
    assert titles == ["held"]


class TestWorkspaceLock:
    @pytest.mark.asyncio
    async def test_a_second_manager_cannot_open_an_open_workspace(self, tmp_path):
        """One workspace belongs to one process; see docs/storage.md."""
        first = DatabaseManager(tmp_path)
        await first.init_archive()
        second = DatabaseManager(tmp_path)
        try:
            with pytest.raises(WorkspaceLockedError):
                await second.init_archive()
        finally:
            await second.close_all()
            await first.close_all()

    @pytest.mark.asyncio
    async def test_close_all_frees_the_workspace(self, tmp_path):
        first = DatabaseManager(tmp_path)
        await first.init_archive()
        await first.close_all()

        second = DatabaseManager(tmp_path)
        await second.init_archive()
        await second.close_all()

    @pytest.mark.asyncio
    async def test_a_failure_creating_imports_releases_the_workspace(self, tmp_path):
        """Ticket 068: the mkdir ran outside the try that releases the lock."""
        (tmp_path / "imports").write_text("a file where the directory should be")
        manager = DatabaseManager(tmp_path)

        with pytest.raises(FileExistsError):
            await manager.init_archive()

        assert not manager._workspace_lock.held
        await manager.close_all()


def test_sources_path_for_is_a_pure_lookup(tmp_path):
    db_manager = DatabaseManager(tmp_path)

    path = db_manager.sources_path_for("abc")

    assert not path.exists()
    assert db_manager.ensure_sources_path_for("abc") == path
    assert path.is_dir()


class TestTransaction:
    @pytest.mark.asyncio
    async def test_it_commits_when_the_block_ends(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "committed")

        async with db_manager.transaction("committed", must_exist=False) as session:
            session.add(DBSpeaker(name="Alice"))

        async with await db_manager.get_project_session("committed") as session:
            names = (await session.execute(select(DBSpeaker.name))).scalars().all()
        assert names == ["Alice"]
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_it_rolls_back_when_the_block_raises(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "rolled-back")

        with pytest.raises(RuntimeError):
            async with db_manager.transaction("rolled-back") as session:
                session.add(DBSpeaker(name="Alice"))
                await session.flush()
                raise RuntimeError("boom")

        async with await db_manager.get_project_session("rolled-back") as session:
            names = (await session.execute(select(DBSpeaker.name))).scalars().all()
        assert names == []
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_an_unknown_chronicle_is_refused_rather_than_created(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await db_manager.init_archive()

        with pytest.raises(LookupError):
            async with db_manager.transaction("never-registered"):
                pass

        assert not (tmp_path / "chronicles" / "never-registered").exists()
        await db_manager.close_all()


class TestLinkedLocation:
    @pytest.mark.asyncio
    async def test_the_location_is_read_once_and_forgotten_on_close(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        linked = tmp_path / "elsewhere" / "project.db"
        await register_chronicle(db_manager, "linked", linked)

        assert await db_manager.project_path_for("linked") == linked
        await forget_chronicle(db_manager, "linked")
        await register_chronicle(db_manager, "linked")

        assert await db_manager.project_path_for("linked") is None
        await db_manager.close_all()

    @pytest.mark.asyncio
    async def test_a_linked_file_that_has_moved_is_refused(self, tmp_path):
        db_manager = DatabaseManager(tmp_path)
        await register_chronicle(db_manager, "moved", tmp_path / "gone" / "project.db")

        with pytest.raises(FileNotFoundError):
            await db_manager.get_project_session("moved", must_exist=True)

        assert not (tmp_path / "gone").exists()
        await db_manager.close_all()
