from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from chronicler.core.container import Container
from chronicler.core.remote import RemoteContainer
from chronicler.core.rpc import RpcServer, service


@service(expose=["echo_id"])
class _UuidEchoService:
    """
    Regression test target: a live smoke test against a real running server found that
    RemoteServiceProxy failed to serialize UUID arguments at all (raised inside httpx's JSON
    encoder, before the request was even sent) - the previous `hasattr(v, "model_dump")`
    check only handled pydantic models, and a bare UUID (the single most common argument
    shape in this codebase - every chronicle_id) has no such method.
    """

    async def echo_id(self, chronicle_id: UUID) -> UUID:
        return chronicle_id


@pytest.mark.asyncio
async def test_remote_proxy_serializes_uuid_arguments():
    container = Container()
    server = RpcServer(container, services=[_UuidEchoService], api_key="key")
    app = server.build()

    the_id = uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        remote = RemoteContainer("http://test", client=client, api_key="key")
        proxy = remote.resolve(_UuidEchoService)

        result = await proxy.echo_id(the_id)

        assert result == the_id
        assert isinstance(result, UUID)


@pytest.mark.asyncio
async def test_remote_proxy_serializes_uuid_keyword_arguments():
    container = Container()
    server = RpcServer(container, services=[_UuidEchoService], api_key="key")
    app = server.build()

    the_id = uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        remote = RemoteContainer("http://test", client=client, api_key="key")
        proxy = remote.resolve(_UuidEchoService)

        result = await proxy.echo_id(chronicle_id=the_id)

        assert result == the_id
