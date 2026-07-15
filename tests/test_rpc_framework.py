import pytest
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
    # 1. Server side
    container = Container()
    # Explicitly set an API key for testing
    api_key = "test-secret-key"
    server = RpcServer(container, services=[MockService], api_key=api_key)
    app = server.build()

    # 2. Test using httpx
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test get_items without key (should fail)
        resp = await client.post("http://test/mock/get_items", json={})
        assert resp.status_code == 401

        # Test get_items with wrong key (should fail)
        resp = await client.post(
            "http://test/mock/get_items", json={}, headers={"X-API-Key": "wrong-key"}
        )
        assert resp.status_code == 403

        # Test get_items with correct key
        resp = await client.post(
            "http://test/mock/get_items", json={}, headers={"X-API-Key": api_key}
        )
        assert resp.status_code == 200
        assert resp.json() == [{"id": 1, "name": "Test Item"}]


@pytest.mark.asyncio
async def test_remote_container_full_cycle():
    # 1. Server side
    container = Container()
    api_key = "remote-test-key"
    server = RpcServer(container, services=[MockService], api_key=api_key)
    app = server.build()

    # 2. Client side with RemoteContainer
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        remote_container = RemoteContainer("http://test", client=client, api_key=api_key)
        proxy = remote_container.resolve(MockService)

        # Test get_items
        items = await proxy.get_items()
        assert len(items) == 1
        assert isinstance(items[0], Item)
        assert items[0].name == "Test Item"

        # Test add_item
        new_item = await proxy.add_item(name="Remote Item")
        assert isinstance(new_item, Item)
        assert new_item.id == 2
        assert new_item.name == "Remote Item"
