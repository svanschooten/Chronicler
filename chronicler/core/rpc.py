import inspect
import secrets
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

_services: list[type] = []

T = TypeVar("T")

EXPOSED_ATTRIBUTE = "__rpc_exposed__"


def service(cls: type[T] | None = None, *, expose: Sequence[str] | None = None) -> Any:
    """
    Registers a class as an RPC service, publishing only the methods it names.

    Exposure is explicit because it used to be implicit: every public coroutine became an
    HTTP route, so making an internal helper async silently published it. See
    docs/deployment-and-rpc.md.
    """

    def decorate(target: type[T]) -> type[T]:
        setattr(target, EXPOSED_ATTRIBUTE, _validated(target, expose or ()))
        if target not in _services:
            _services.append(target)
        return target

    return decorate if cls is None else decorate(cls)


def _validated(cls: type, names: Sequence[str]) -> tuple[str, ...]:
    for name in names:
        method = getattr(cls, name, None)
        if method is None:
            raise ValueError(f"{cls.__name__} exposes {name!r}, which it does not define")
        if not inspect.iscoroutinefunction(method):
            raise ValueError(f"{cls.__name__}.{name} is exposed but is not a coroutine")
    return tuple(sorted(names))


def exposed_methods(cls: type) -> list[str]:
    """The method names this class publishes over RPC, in a stable order."""
    return list(cls.__dict__.get(EXPOSED_ATTRIBUTE, ()))


def get_services() -> list[type]:
    return _services


class RpcServer:
    MAX_UPLOAD_SIZE = 500 * 1024 * 1024
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

    def _register_service(self, app: Any, service_cls: type):
        from fastapi import APIRouter

        cls_name = service_cls.__name__
        if cls_name.endswith("Service"):
            prefix = "/" + cls_name[:-7].lower()
        else:
            prefix = "/" + cls_name.lower()

        router = APIRouter(prefix=prefix)

        for name in exposed_methods(service_cls):
            self._add_route(router, service_cls, getattr(service_cls, name), name)

        app.include_router(router)

    def _add_route(self, router: Any, service_cls: type, method: Callable, name: str):
        from fastapi import Body
        from sqlalchemy.ext.asyncio import AsyncSession

        sig = inspect.signature(method)

        new_params = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                new_params.append(param)
                continue

            original_default = (
                param.default if param.default is not inspect.Parameter.empty else ...
            )
            new_param = param.replace(default=Body(original_default, alias=param_name, embed=True))
            new_params.append(new_param)

        new_sig = sig.replace(parameters=new_params)

        async def wrapper(*args, **kwargs):
            if self.container is None:
                raise RuntimeError("RpcServer has no container configured")
            scope = self.container.create_scope()
            try:
                instance = scope.resolve(service_cls)
                bound_method = getattr(instance, name)
                return await bound_method(*args, **kwargs)
            finally:
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
            for service_cls in target_services:
                self._register_service(self._app, service_cls)

        return self._app
