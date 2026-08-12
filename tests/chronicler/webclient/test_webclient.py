import pytest
from httpx import ASGITransport, AsyncClient

from chronicler.webclient.main import create_app


@pytest.mark.asyncio
async def test_webclient_serves_index():
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "Chronicler" in response.text

        response = await client.get("/config")
        assert response.status_code == 200
