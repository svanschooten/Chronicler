import inspect
import logging
import secrets
from collections.abc import Callable
from typing import Any, TypeVar

_services: list[type] = []

T = TypeVar("T")


def service(cls: type[T]) -> type[T]:
    if cls not in _services:
        _services.append(cls)
    return cls


def get_services() -> list[type]:
    return _services


class RpcServer:
    MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB - generous headroom for audio files
    UPLOAD_CHUNK_SIZE = 1024 * 1024

    def __init__(
        self,
        container: Any = None,
        services: list[type] = None,
        api_key: str | None = None,
    ):
        self.container = container
        self.services = services
        self.api_key = api_key or secrets.token_urlsafe(32)
        self._app: Any = None
        self._instances: list[Any] = []

    def register(self, instance: Any):
        self._instances.append(instance)

    def _register_instance(self, app: Any, instance: Any):
        from fastapi import APIRouter

        cls_name = instance.__class__.__name__
        service_name = cls_name
        if service_name.endswith("Service"):
            prefix = "/" + service_name[:-7].lower()
        else:
            prefix = "/" + service_name.lower()

        router = APIRouter(prefix=prefix)

        for name, method in inspect.getmembers(instance, inspect.iscoroutinefunction):
            if name.startswith("_"):
                continue

            self._add_route(router, method, name)

        app.include_router(router)

    def _add_route(self, router: Any, method: Callable, name: str):
        from fastapi import Body

        sig = inspect.signature(method)

        new_params = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Variadic parameters (*args, **kwargs) cannot have default values
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                new_params.append(param)
                continue

            # Treat all parameters as body fields
            new_param = param.replace(default=Body(..., alias=param_name, embed=True))
            new_params.append(new_param)

        new_sig = sig.replace(parameters=new_params)

        async def wrapper(*args, **kwargs):
            return await method(*args, **kwargs)

        wrapper.__signature__ = new_sig  # type: ignore
        wrapper.__name__ = name
        wrapper.__annotations__ = method.__annotations__

        router.add_api_route(f"/{name}", wrapper, methods=["POST"])

    def build(self):
        import uuid
        from pathlib import Path

        from fastapi import Depends, FastAPI, File, HTTPException, Security, UploadFile, status
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.security import APIKeyHeader

        from chronicler.core.database_manager import DatabaseManager

        api_key_header = APIKeyHeader(name="X-API-Key")

        async def verify_api_key(api_key: str = Security(api_key_header)):
            if not secrets.compare_digest(api_key, self.api_key):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Could not validate credentials",
                )
            return api_key

        self._app = FastAPI(
            title="Chronicler RPC Server",
            dependencies=[Depends(verify_api_key)],
        )

        # Auth here is a bearer-style X-API-Key header, not a cookie, so browsers never
        # attach it automatically the way they do credentials - allow_credentials=True
        # combined with a wildcard origin would be both invalid (browsers reject the
        # combination) and unnecessary here.
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @self._app.post("/upload")
        async def upload_file(file: UploadFile = File(...)):
            if not self.container:
                raise HTTPException(status_code=500, detail="Server not configured for uploads")

            db_manager = self.container.resolve(DatabaseManager)
            upload_dir = db_manager.get_imports_path()

            # file.filename is fully client-controlled - never use it to build a path
            # (e.g. "../../.ssh/authorized_keys" would escape upload_dir). Generate the
            # on-disk name server-side; keep only a whitelisted extension for
            # readability, and store the original name as metadata, not as a path.
            raw_suffix = Path(file.filename).suffix if file.filename else ""
            safe_suffix = "".join(c for c in raw_suffix if c.isalnum() or c == ".")[:16]
            stored_name = f"{uuid.uuid4().hex}{safe_suffix}"
            file_path = upload_dir / stored_name

            bytes_written = 0
            try:
                with file_path.open("wb") as buffer:
                    while chunk := await file.read(self.UPLOAD_CHUNK_SIZE):
                        bytes_written += len(chunk)
                        if bytes_written > self.MAX_UPLOAD_SIZE:
                            raise HTTPException(
                                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                                detail=(
                                    f"File exceeds maximum upload size of "
                                    f"{self.MAX_UPLOAD_SIZE} bytes"
                                ),
                            )
                        buffer.write(chunk)
            except HTTPException:
                file_path.unlink(missing_ok=True)
                raise

            return {"file_path": str(file_path), "original_filename": file.filename}

        if self.container:
            target_services = self.services if self.services is not None else get_services()
            for cls in target_services:
                instance = self.container.resolve(cls)
                self.register(instance)

        for instance in self._instances:
            self._register_instance(self._app, instance)

        return self._app

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        import uvicorn

        logger = logging.getLogger(__name__)
        logger.info(f"RPC Server API Key: {self.api_key}")
        app = self.build()
        uvicorn.run(app, host=host, port=port, log_config=None)
