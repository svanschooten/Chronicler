import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from chronicler.core.config import get_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Chronicler Web Client")

    static_path = Path(__file__).parent / "src"

    app.mount("/src", StaticFiles(directory=static_path), name="src")

    def _not_configured() -> JSONResponse:
        return JSONResponse(
            {"detail": "Web client is not configured with a server_url/api_key"},
            status_code=503,
        )

    @app.get("/config")
    async def get_config():
        settings = get_settings()
        return {"connected": bool(settings.server_url and settings.api_key)}

    @app.post("/api/upload")
    async def proxy_upload(request: Request):
        settings = get_settings()
        if not settings.server_url or not settings.api_key:
            return _not_configured()

        body = await request.body()
        headers = {"X-API-Key": settings.api_key}
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type

        async with httpx.AsyncClient() as client:
            try:
                upstream = await client.post(
                    f"{settings.server_url}/upload",
                    content=body,
                    headers=headers,
                    timeout=120.0,
                )
            except httpx.HTTPError:
                logger.exception("Upstream upload request failed")
                return JSONResponse({"detail": "Upstream server unreachable"}, status_code=502)

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )

    @app.post("/api/{service}/{method}")
    async def proxy_rpc(service: str, method: str, request: Request):
        settings = get_settings()
        if not settings.server_url or not settings.api_key:
            return _not_configured()

        body = await request.body()
        headers = {"X-API-Key": settings.api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            try:
                upstream = await client.post(
                    f"{settings.server_url}/{service}/{method}",
                    content=body,
                    headers=headers,
                    timeout=30.0,
                )
            except httpx.HTTPError:
                logger.exception("Upstream RPC request failed")
                return JSONResponse({"detail": "Upstream server unreachable"}, status_code=502)

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )

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
