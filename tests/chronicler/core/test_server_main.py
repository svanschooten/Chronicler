import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.local_container import register_local_repositories
from chronicler.core.models import Chronicle, TranscriptLine
from chronicler.core.repositories import TaskRepository
from chronicler.core.rpc import RpcServer, service
from chronicler.core.services import ChronicleService, SearchService, TaskService, TranscriptService
from chronicler.core.sqlite import (
    SQLiteChronicleRepository,
    SQLiteTaskRepository,
    SQLiteTranscriptRepository,
)


@service
class _SessionIdProbeService:
    """Test-only service exposing which AsyncSession backs its repository, so tests
    can prove each request gets a fresh one rather than reaching into RpcServer
    internals.
    """

    def __init__(self, repository: TaskRepository):
        self.repository = repository

    async def session_id(self) -> int:
        return id(self.repository.session)  # type: ignore[attr-defined]


def _build_server_app(tmp_path, api_key: str = "test-key"):
    """Mirrors the wiring in chronicler/server/main.py::run_server."""
    db_manager = DatabaseManager(tmp_path)

    container = Container()
    register_local_repositories(container, db_manager)

    server = RpcServer(
        container,
        services=[ChronicleService, SearchService, TaskService, TranscriptService],
        api_key=api_key,
    )
    return db_manager, server.build()


@pytest.mark.asyncio
async def test_server_builds_without_error(tmp_path):
    db_manager, app = _build_server_app(tmp_path)
    try:
        await db_manager.init_archive()
        assert app is not None
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_search_service_resolves(tmp_path):
    """Reproduces the historical blocker directly: resolving SearchService used to raise
    TypeError because SQLiteTagRepository didn't implement the abstract `search` method.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        container = Container()
        register_local_repositories(container, db_manager)

        search_service = container.resolve(SearchService)
        assert search_service is not None
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_server_routes_reject_missing_key(tmp_path):
    db_manager, app = _build_server_app(tmp_path)
    try:
        await db_manager.init_archive()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/chronicle/list_chronicles", json={})
            assert resp.status_code == 401

            # Routing successfully reaches the auth dependency for SearchService at all
            # is itself meaningful: before the fix, resolving SearchService raised
            # TypeError while the app was still being built, so this route didn't exist.
            resp = await client.post("/search/search_tags", json={"query": ""})
            assert resp.status_code == 401

            resp = await client.post("/task/list_tasks", json={})
            assert resp.status_code == 401
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_server_routes_respond_with_valid_key(tmp_path):
    db_manager, app = _build_server_app(tmp_path, api_key="valid-key")
    try:
        await db_manager.init_archive()

        headers = {"X-API-Key": "valid-key"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/chronicle/list_chronicles", json={}, headers=headers)
            assert resp.status_code == 200
            assert resp.json() == []

            resp = await client.post("/task/list_tasks", json={}, headers=headers)
            assert resp.status_code == 200
            assert resp.json() == []

            # NOTE: /search/* routes are intentionally not exercised here past auth.
            # SearchService's methods raise NotImplementedError (Sprint 4 scope, see
            # search_service.py) - a 500 either way, but a clear one now rather than the
            # confusing ResponseValidationError they used to produce by returning None
            # against a `-> list[...]` annotation. That's separate from the bug this
            # test file targets (SQLiteTagRepository.search missing).
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_each_request_gets_a_fresh_session(tmp_path):
    """Before this sprint, RpcServer resolved each service once at build() time, so
    every request shared one AsyncSession for the server's entire lifetime - unsafe
    under concurrent use. Each request must now see a distinct session.
    """
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        container = Container()
        container.register_instance(DatabaseManager, db_manager)
        container.register_factory(AsyncSession, lambda: db_manager.get_archive_session())
        container.register_factory(TaskRepository, SQLiteTaskRepository)  # type: ignore[type-abstract]

        server = RpcServer(
            container, services=[_SessionIdProbeService], api_key="probe-key"
        )
        app = server.build()

        headers = {"X-API-Key": "probe-key"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.post(
                "/_sessionidprobe/session_id", json={}, headers=headers
            )
            resp2 = await client.post(
                "/_sessionidprobe/session_id", json={}, headers=headers
            )
            assert resp1.status_code == 200
            assert resp2.status_code == 200
            assert resp1.json() != resp2.json()
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_request_scoped_session_is_closed_after_request(tmp_path, monkeypatch):
    db_manager = DatabaseManager(tmp_path)
    try:
        await db_manager.init_archive()

        container = Container()
        container.register_instance(DatabaseManager, db_manager)
        container.register_factory(AsyncSession, lambda: db_manager.get_archive_session())
        container.register_factory(TaskRepository, SQLiteTaskRepository)  # type: ignore[type-abstract]

        server = RpcServer(
            container, services=[_SessionIdProbeService], api_key="probe-key"
        )
        app = server.build()

        close_calls = 0
        original_close = AsyncSession.close

        async def counting_close(self):
            nonlocal close_calls
            close_calls += 1
            await original_close(self)

        monkeypatch.setattr(AsyncSession, "close", counting_close)

        headers = {"X-API-Key": "probe-key"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/_sessionidprobe/session_id", json={}, headers=headers
            )
            assert resp.status_code == 200

        assert close_calls == 1
    finally:
        await db_manager.close_all()


@pytest.mark.asyncio
async def test_transcript_reachable_over_rpc(tmp_path):
    """TranscriptService wasn't registered as an RPC service at all before this sprint
    - there was no way to reach it remotely, which is why Thin Client transcript
    viewing didn't work. Confirms it's reachable and returns real data end to end.
    """
    db_manager, app = _build_server_app(tmp_path, api_key="valid-key")
    try:
        await db_manager.init_archive()

        archive_session = db_manager.get_archive_session()
        async with archive_session:
            chronicle = await SQLiteChronicleRepository(archive_session).create(
                Chronicle(title="Remote Session")
            )

        project_session = await db_manager.get_project_session(str(chronicle.id))
        async with project_session:
            repo = SQLiteTranscriptRepository(project_session)
            speaker = await repo.get_or_create_speaker("Alice")
            await repo.add_line(
                TranscriptLine(speaker_id=speaker.id, start_time=0.0, end_time=1.0, text="Hi")
            )
            await project_session.commit()

        headers = {"X-API-Key": "valid-key"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/transcript/get_transcript",
                json={"chronicle_id": str(chronicle.id)},
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["text"] == "Hi"
            assert data[0]["speaker_name"] == "Alice"
    finally:
        await db_manager.close_all()
