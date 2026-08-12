import io

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from chronicler.core.container import Container
from chronicler.core.remote import RemoteContainer
from chronicler.core.rpc import RpcServer, service


class Item(BaseModel):
    id: int
    name: str


@service
class MockService:
    async def get_items(self) -> list[Item]:
        return [Item(id=1, name="Test Item")]

    async def add_item(self, name: str) -> Item:
        return Item(id=2, name=name)


@pytest.mark.asyncio
async def test_rpc_server_and_remote_proxy():
    container = Container()
    api_key = "test-secret-key"
    server = RpcServer(container, services=[MockService], api_key=api_key)
    app = server.build()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing key
        resp = await client.post("http://test/mock/get_items", json={})
        assert resp.status_code == 401

        # Wrong key
        resp = await client.post(
            "http://test/mock/get_items", json={}, headers={"X-API-Key": "wrong-key"}
        )
        assert resp.status_code == 403

        # Correct key
        resp = await client.post(
            "http://test/mock/get_items", json={}, headers={"X-API-Key": api_key}
        )
        assert resp.status_code == 200
        assert resp.json() == [{"id": 1, "name": "Test Item"}]


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


@pytest.mark.asyncio
async def test_rpc_server_upload(tmp_path):
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

    # services=[] deliberately: this test only exercises /upload, and leaving the
    # default (None -> every globally @service-registered class) would make the test's
    # pass/fail depend on which other test modules happened to import first in this
    # session and populate the global registry.
    server = RpcServer(container=container, services=[], api_key="test-key")
    app = server.build()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("test.wav", io.BytesIO(b"dummy audio"), "audio/wav")}
        response = await client.post("/upload", files=files, headers={"X-API-Key": "test-key"})
        assert response.status_code == 200
        data = response.json()
        assert "file_path" in data

        import os

        assert os.path.exists(data["file_path"])
