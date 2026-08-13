import pytest
from sqlalchemy import select, text

from chronicler.core.database import DBChronicle
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.project_database import DBSpeaker


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

    async with await db_manager.get_project_session(chronicle_id) as session:
        result = await session.execute(select(DBSpeaker))
        assert result.scalars().all() == []

    assert (tmp_path / "chronicles" / chronicle_id / "project.db").exists()

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
    await db_manager.init_archive()  # must not raise

    async with db_manager.get_archive_session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM alembic_version"))
        assert result.scalar_one() == 1

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_project_session_stamps_alembic_head(tmp_path):
    db_manager = DatabaseManager(tmp_path)

    session = await db_manager.get_project_session("test-chronicle")
    async with session:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        assert result.scalar_one() == _head_revision("project")

    await db_manager.close_all()


@pytest.mark.asyncio
async def test_project_session_opened_twice_is_a_noop_not_an_error(tmp_path):
    """Simulates navigating to the same chronicle's transcript view twice."""
    db_manager = DatabaseManager(tmp_path)

    session1 = await db_manager.get_project_session("test-chronicle")
    await session1.close()
    session2 = await db_manager.get_project_session("test-chronicle")  # must not raise

    async with session2:
        result = await session2.execute(text("SELECT COUNT(*) FROM alembic_version"))
        assert result.scalar_one() == 1

    await db_manager.close_all()
