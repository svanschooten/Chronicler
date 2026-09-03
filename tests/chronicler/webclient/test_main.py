from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from chronicler.core.config import Settings
from chronicler.core.container import Container
from chronicler.core.rpc import RpcServer, service
from chronicler.webclient.main import create_app


@pytest.mark.asyncio
async def test_webclient_serves_index():
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "Chronicler" in response.text


@pytest.mark.asyncio
async def test_config_never_leaks_api_key():
    settings = Settings(server_url="http://upstream:8000", api_key="super-secret-key")
    app = create_app()

    with patch("chronicler.webclient.main.get_settings", return_value=settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/config")
            assert response.status_code == 200
            body = response.json()

            assert "api_key" not in body
            assert "super-secret-key" not in response.text
            assert "server_url" not in body
            assert body == {"connected": True}


@pytest.mark.asyncio
async def test_config_reports_not_connected_when_unconfigured():
    settings = Settings(server_url=None, api_key=None)
    app = create_app()

    with patch("chronicler.webclient.main.get_settings", return_value=settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/config")
            assert response.json() == {"connected": False}


@service
class _MockUpstreamService:
    async def echo(self, value: str) -> str:
        return value


@pytest.mark.asyncio
async def test_proxy_injects_api_key_server_side():
    """
    The browser calls /api/{service}/{method} with no key at all; the web client must attach
    X-API-Key itself when forwarding upstream, and the browser-facing response must never
    contain the key.
    """
    upstream_container = Container()
    upstream_server = RpcServer(
        upstream_container, services=[_MockUpstreamService], api_key="real-upstream-key"
    )
    upstream_app = upstream_server.build()
    upstream_transport = ASGITransport(app=upstream_app)

    real_async_client = httpx.AsyncClient

    def _upstream_client_factory(*args, **kwargs):
        return real_async_client(transport=upstream_transport, base_url="http://upstream")

    settings = Settings(server_url="http://upstream", api_key="real-upstream-key")
    webclient_app = create_app()

    with (
        patch("chronicler.webclient.main.get_settings", return_value=settings),
        patch("chronicler.webclient.main.httpx.AsyncClient", side_effect=_upstream_client_factory),
    ):
        webclient_transport = ASGITransport(app=webclient_app)
        async with AsyncClient(transport=webclient_transport, base_url="http://browser") as browser:
            response = await browser.post("/api/_mockupstream/echo", json={"value": "hello"})
            assert response.status_code == 200
            assert response.json() == "hello"
            assert "real-upstream-key" not in response.text


@pytest.mark.asyncio
async def test_proxy_rejects_when_unconfigured():
    settings = Settings(server_url=None, api_key=None)
    app = create_app()

    with patch("chronicler.webclient.main.get_settings", return_value=settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chronicle/list_chronicles", json={})
            assert response.status_code == 503
