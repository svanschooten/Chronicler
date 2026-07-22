import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from chronicler.core.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Chronicler Web Client")

    static_path = Path(__file__).parent / "src"

    # Mount the static files directory
    app.mount("/src", StaticFiles(directory=static_path), name="src")

    @app.get("/config")
    async def get_config():
        settings = get_settings()
        return {
            "server_url": settings.server_url or "http://localhost:8000",
            "api_key": settings.api_key,
        }

    @app.get("/")
    async def read_index():
        return FileResponse(static_path / "index.html")

    return app


def run_server(host: str = "0.0.0.0", port: int = 8080):
    import uvicorn

    logger = logging.getLogger(__name__)
    logger.info("Chronicler Webclient Server starting...")

    app = create_app()
    uvicorn.run(app, host=host, port=port)
