import inspect
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
        services: list[type] | None = None,
        api_key: str | None = None,
    ):
        self.container = container
        self.services = services
        self.api_key = api_key or secrets.token_urlsafe(32)
        self._app: Any = None
        self._service_classes: list[type] = []

    def register(self, service_cls: type):
        self._service_classes.append(service_cls)

    def _register_service(self, app: Any, service_cls: type):
        from fastapi import APIRouter

        cls_name = service_cls.__name__
        if cls_name.endswith("Service"):
            prefix = "/" + cls_name[:-7].lower()
        else:
            prefix = "/" + cls_name.lower()

        router = APIRouter(prefix=prefix)

        for name, method in inspect.getmembers(service_cls, inspect.iscoroutinefunction):
            if name.startswith("_"):
                continue

            self._add_route(router, service_cls, method, name)

        app.include_router(router)

    def _add_route(self, router: Any, service_cls: type, method: Callable, name: str):
        from fastapi import Body
        from sqlalchemy.ext.asyncio import AsyncSession

        sig = inspect.signature(method)

        new_params = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Variadic parameters (*args, **kwargs) cannot have default values
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                new_params.append(param)
                continue

            # Treat all parameters as body fields, preserving the method's own
            # default (including None) rather than always using Body(...) (Ellipsis =
            # required) - that unconditionally made every parameter mandatory
            # regardless of the method's actual signature, so any caller (a
            # RemoteContainer proxy or otherwise) that omitted or explicitly passed
            # None for a genuinely optional argument got a 422.
            original_default = (
                param.default if param.default is not inspect.Parameter.empty else ...
            )
            new_param = param.replace(
                default=Body(original_default, alias=param_name, embed=True)
            )
            new_params.append(new_param)

        new_sig = sig.replace(parameters=new_params)

        async def wrapper(*args, **kwargs):
            # A fresh scope per request: a fresh AsyncSession, fresh repositories, a
            # fresh service instance. Only DatabaseManager (an explicit singleton) is
            # shared across requests - see Container.create_scope(). Without this,
            # every request would share one AsyncSession for the server's entire
            # lifetime, which isn't safe under concurrent use.
            if self.container is None:
                raise RuntimeError("RpcServer has no container configured")
            scope = self.container.create_scope()
            try:
                instance = scope.resolve(service_cls)
                bound_method = getattr(instance, name)
                return await bound_method(*args, **kwargs)
            finally:
                # Only if this scope actually built one - a service with no
                # database dependency (e.g. tests using a bare Container()) should
                # not trigger Container's auto-build fallback for AsyncSession, which
                # isn't constructible without a bound engine and would raise.
                if scope.is_registered(AsyncSession):
                    await scope.resolve(AsyncSession).close()

        wrapper.__signature__ = new_sig  # type: ignore
        wrapper.__name__ = name
        wrapper.__annotations__ = method.__annotations__

        router.add_api_route(f"/{name}", wrapper, methods=["POST"])

    def build(self):
        from fastapi import Depends, FastAPI, File, HTTPException, Security, UploadFile, status
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.security import APIKeyHeader

        from chronicler.core.database_manager import DatabaseManager
        from chronicler.core.file_staging import sanitize_stage_name

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
            file_path = upload_dir / sanitize_stage_name(file.filename)

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
                self.register(cls)

        for service_cls in self._service_classes:
            self._register_service(self._app, service_cls)

        return self._app
