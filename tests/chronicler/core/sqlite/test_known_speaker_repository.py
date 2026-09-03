import pytest
import pytest_asyncio

from chronicler.core.database_manager import DatabaseManager
from chronicler.core.sqlite import SQLiteKnownSpeakerRepository


@pytest_asyncio.fixture
async def repo(tmp_path):
    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()
    session = db_manager.get_archive_session()
    try:
        yield SQLiteKnownSpeakerRepository(session), session
    finally:
        await session.close()
        await db_manager.close_all()


class TestRegister:
    @pytest.mark.asyncio
    async def test_records_a_new_speaker(self, repo):
        repository, session = repo

        await repository.register("Alice")
        await session.commit()

        assert await repository.list_names() == ["Alice"]

    @pytest.mark.asyncio
    async def test_registering_twice_keeps_one_row(self, repo):
        repository, session = repo

        await repository.register("Alice")
        await repository.register("Alice")
        await session.commit()

        assert await repository.list_names() == ["Alice"]

    @pytest.mark.asyncio
    async def test_re_registering_counts_a_use(self, repo):
        repository, session = repo

        await repository.register("Alice")
        await repository.register("Alice")
        await session.commit()

        speakers = await repository.list_speakers()
        assert speakers[0].uses == 2

    @pytest.mark.asyncio
    async def test_names_differing_only_by_case_are_the_same_speaker(self, repo):
        repository, session = repo

        await repository.register("Alice")
        await repository.register("alice")
        await session.commit()

        assert await repository.list_names() == ["Alice"]

    @pytest.mark.asyncio
    async def test_surrounding_whitespace_is_ignored(self, repo):
        repository, session = repo

        await repository.register("  Alice  ")
        await session.commit()

        assert await repository.list_names() == ["Alice"]

    @pytest.mark.asyncio
    async def test_a_blank_name_is_not_registered(self, repo):
        repository, session = repo

        await repository.register("   ")
        await session.commit()

        assert await repository.list_names() == []


class TestListing:
    @pytest.mark.asyncio
    async def test_names_are_sorted_alphabetically(self, repo):
        repository, session = repo
        for name in ("Carol", "alice", "Bob"):
            await repository.register(name)
        await session.commit()

        assert await repository.list_names() == ["alice", "Bob", "Carol"]

    @pytest.mark.asyncio
    async def test_search_matches_a_substring_case_insensitively(self, repo):
        repository, session = repo
        for name in ("Alice", "Bob", "Malice"):
            await repository.register(name)
        await session.commit()

        assert await repository.search("ali") == ["Alice", "Malice"]

    @pytest.mark.asyncio
    async def test_search_escapes_wildcards(self, repo):
        repository, session = repo
        for name in ("Alice", "100%"):
            await repository.register(name)
        await session.commit()

        assert await repository.search("%") == ["100%"]

    @pytest.mark.asyncio
    async def test_an_empty_registry_lists_nothing(self, repo):
        repository, _ = repo

        assert await repository.list_names() == []
