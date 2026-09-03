import inspect
import io
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from chronicler.core.container import Container
from chronicler.core.remote import RemoteContainer
from chronicler.core.rpc import RpcServer, exposed_methods, get_services, service


class Item(BaseModel):
    id: int
    name: str


@service(expose=["add_item", "add_item_with_note", "get_items"])
class MockService:
    async def get_items(self) -> list[Item]:
        return [Item(id=1, name="Test Item")]

    async def add_item(self, name: str) -> Item:
        return Item(id=2, name=name)

    async def add_item_with_note(self, name: str, note: str | None = None) -> Item:
        return Item(id=3, name=f"{name} ({note})" if note else name)


@pytest.mark.asyncio
async def test_rpc_server_and_remote_proxy():
    container = Container()
    api_key = "test-secret-key"
    server = RpcServer(container, services=[MockService], api_key=api_key)
    app = server.build()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("http://test/mock/get_items", json={})
        assert resp.status_code == 401

        resp = await client.post(
            "http://test/mock/get_items", json={}, headers={"X-API-Key": "wrong-key"}
        )
        assert resp.status_code == 403

        resp = await client.post(
            "http://test/mock/get_items", json={}, headers={"X-API-Key": api_key}
        )
        assert resp.status_code == 200
        assert resp.json() == [{"id": 1, "name": "Test Item"}]


@pytest.mark.asyncio
async def test_optional_parameters_stay_optional_over_rpc():
    """
    _add_route used to wrap every parameter as Body(..., ...) unconditionally - Ellipsis
    means required in FastAPI/Pydantic, discarding the method's own default regardless of
    what it was.
    """
    container = Container()
    api_key = "test-secret-key"
    server = RpcServer(container, services=[MockService], api_key=api_key)
    app = server.build()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"X-API-Key": api_key}

        resp = await client.post(
            "http://test/mock/add_item_with_note", json={"name": "a"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "a"

        resp = await client.post(
            "http://test/mock/add_item_with_note",
            json={"name": "b", "note": None},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "b"

        resp = await client.post(
            "http://test/mock/add_item_with_note",
            json={"name": "c", "note": "urgent"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "c (urgent)"


def test_cors_does_not_combine_wildcard_with_credentials():
    """
    allow_origins=['*'] together with allow_credentials=True is an invalid, unsafe
    combination that browsers reject outright - and unnecessary here anyway, since auth is a
    bearer-style X-API-Key header that browsers never attach automatically.
    """
    container = Container()
    server = RpcServer(container, services=[], api_key="test-key")
    app = server.build()

    cors_middlewares = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert len(cors_middlewares) == 1
    assert cors_middlewares[0].kwargs["allow_credentials"] is False


@pytest.mark.asyncio
async def test_wrong_key_of_same_length_still_rejected():
    """
    Exercises the secrets.compare_digest path with a same-length wrong key, since a naive
    `!=` and compare_digest both reject it - the point is the endpoint stays correct after
    switching comparison functions, not that we can observe timing here.
    """
    container = Container()
    api_key = "a" * 32
    server = RpcServer(container, services=[MockService], api_key=api_key)
    app = server.build()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "http://test/mock/get_items", json={}, headers={"X-API-Key": "b" * 32}
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remote_container_full_cycle():
    container = Container()
    api_key = "remote-test-key"
    server = RpcServer(container, services=[MockService], api_key=api_key)
    app = server.build()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        remote_container = RemoteContainer("http://test", client=client, api_key=api_key)
        proxy = remote_container.resolve(MockService)

        items = await proxy.get_items()
        assert len(items) == 1
        assert isinstance(items[0], Item)
        assert items[0].name == "Test Item"

        new_item = await proxy.add_item(name="Remote Item")
        assert isinstance(new_item, Item)
        assert new_item.id == 2
        assert new_item.name == "Remote Item"


async def _build_upload_app(tmp_path):
    from sqlalchemy.ext.asyncio import AsyncSession

    from chronicler.core.database_manager import DatabaseManager
    from chronicler.core.repositories import ChronicleRepository, TagRepository, TaskRepository
    from chronicler.core.sqlite import (
        SQLiteChronicleRepository,
        SQLiteTagRepository,
        SQLiteTaskRepository,
    )

    db_manager = DatabaseManager(tmp_path)
    await db_manager.init_archive()

    container = Container()
    container.register_instance(DatabaseManager, db_manager)
    container.register_factory(AsyncSession, lambda: db_manager.get_archive_session())
    container.register_factory(ChronicleRepository, SQLiteChronicleRepository)
    container.register_factory(TaskRepository, SQLiteTaskRepository)
    container.register_factory(TagRepository, SQLiteTagRepository)

    server = RpcServer(container=container, services=[], api_key="test-key")
    return server.build(), db_manager.get_imports_path()


@pytest.mark.asyncio
async def test_rpc_server_upload(tmp_path):
    app, upload_dir = await _build_upload_app(tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("test.wav", io.BytesIO(b"dummy audio"), "audio/wav")}
        response = await client.post("/upload", files=files, headers={"X-API-Key": "test-key"})
        assert response.status_code == 200
        data = response.json()
        assert "file_path" in data
        assert data["original_filename"] == "test.wav"

        result_path = Path(data["file_path"])
        assert result_path.exists()
        assert result_path.name != "test.wav"
        assert result_path.suffix == ".wav"
        assert result_path.parent.resolve() == upload_dir.resolve()


@pytest.mark.asyncio
async def test_upload_rejects_path_traversal_filename(tmp_path):
    app, upload_dir = await _build_upload_app(tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for evil_name in (
            "../../../etc/passwc",
            "..%2f..%2fetc%2fpasswd",
            "/etc/passwd",
            "..\\..\\windows\\system32\\config",
        ):
            files = {"file": (evil_name, io.BytesIO(b"data"), "application/octet-stream")}
            response = await client.post("/upload", files=files, headers={"X-API-Key": "test-key"})
            assert response.status_code == 200
            result_path = Path(response.json()["file_path"]).resolve()
            assert result_path.is_relative_to(upload_dir.resolve()), evil_name


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(RpcServer, "MAX_UPLOAD_SIZE", 10)
    app, upload_dir = await _build_upload_app(tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("big.wav", io.BytesIO(b"x" * 1000), "audio/wav")}
        response = await client.post("/upload", files=files, headers={"X-API-Key": "test-key"})
        assert response.status_code == 413

    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_same_filename_twice_no_collision(tmp_path):
    app, upload_dir = await _build_upload_app(tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        paths = []
        for _ in range(2):
            files = {"file": ("session.txt", io.BytesIO(b"hello"), "text/plain")}
            response = await client.post("/upload", files=files, headers={"X-API-Key": "test-key"})
            assert response.status_code == 200
            paths.append(response.json()["file_path"])

        assert paths[0] != paths[1]
        assert all(Path(p).exists() for p in paths)


class TestExplicitExposure:
    def test_a_service_publishes_only_what_it_names(self):
        @service(expose=["wanted"])
        class Sample:
            async def wanted(self) -> str:
                return "yes"

            async def internal_helper(self) -> str:
                return "no"

        assert exposed_methods(Sample) == ["wanted"]

    def test_naming_a_method_that_does_not_exist_fails_at_import_time(self):
        with pytest.raises(ValueError, match="typo"):

            @service(expose=["typo"])
            class Sample:
                async def real(self) -> str:
                    return "x"

    def test_naming_a_non_async_method_fails_at_import_time(self):
        """Only coroutines can be served; a sync method would silently never be routed."""
        with pytest.raises(ValueError, match="coroutine"):

            @service(expose=["sync_one"])
            class Sample:
                def sync_one(self) -> str:
                    return "x"

    def test_a_service_with_no_expose_list_publishes_nothing(self):
        @service
        class Sample:
            async def anything(self) -> str:
                return "x"

        assert exposed_methods(Sample) == []

    def test_an_unregistered_class_exposes_nothing(self):
        class NotAService:
            async def anything(self) -> str:
                return "x"

        assert exposed_methods(NotAService) == []

    def test_the_exposed_list_is_sorted_so_the_surface_is_reviewable(self):
        @service(expose=["zebra", "apple"])
        class Sample:
            async def zebra(self) -> str:
                return "z"

            async def apple(self) -> str:
                return "a"

        assert exposed_methods(Sample) == ["apple", "zebra"]


class TestTheRealServices:
    def test_no_internal_helper_is_published(self):
        """
        Regression test: making a helper async used to publish it. `sources_dir` and
        `source_path` became HTTP endpoints that way and leaked server paths.
        """
        from chronicler.core.services.transcript_service import TranscriptService

        published = exposed_methods(TranscriptService)

        assert "sources_dir" not in published
        assert "source_path" not in published
        assert "mark_source_transcribed" not in published

    def test_every_published_method_exists_and_is_async(self):
        for cls in get_services():
            for name in exposed_methods(cls):
                method = getattr(cls, name, None)
                assert method is not None, f"{cls.__name__}.{name}"
                assert inspect.iscoroutinefunction(method), f"{cls.__name__}.{name}"

    def test_the_published_surface_is_what_we_think_it_is(self):
        """
        Counted per service rather than off `get_services()`, which is process-global and
        collects the test-only services other modules register.
        """
        from chronicler.core.services import (
            ChronicleService,
            SystemService,
            TaskService,
            TranscriptService,
        )

        surface = {
            cls.__name__: len(exposed_methods(cls))
            for cls in (ChronicleService, TranscriptService, TaskService, SystemService)
        }

        assert surface == {
            "ChronicleService": 8,
            "TranscriptService": 13,
            "TaskService": 8,
            "SystemService": 4,
        }
