import io

import pytest
from httpx import ASGITransport, AsyncClient

from chronicler.core.rpc import RpcServer


@pytest.mark.asyncio
async def test_rpc_server_upload(tmp_path):
    from sqlalchemy.ext.asyncio import AsyncSession

    from chronicler.core.container import Container
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

    server = RpcServer(container=container, api_key="test-key")
    app = server.build()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("test.wav", io.BytesIO(b"dummy audio"), "audio/wav")}
        response = await client.post("/upload", files=files, headers={"X-API-Key": "test-key"})
        assert response.status_code == 200
        data = response.json()
        assert "file_path" in data
        assert "test.wav" in data["file_path"]

        # Verify file exists
        import os

        assert os.path.exists(data["file_path"])


# We will implement the /upload endpoint and then update this test
