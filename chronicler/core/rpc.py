import inspect
import secrets
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

_services: list[type] = []

T = TypeVar("T")

EXPOSED_ATTRIBUTE = "__rpc_exposed__"

BINARY_RETURNS = (bytes, bytearray)
BINARY_MEDIA_TYPE = "application/octet-stream"
FILE_RETURN = Path
"""A method returning a `Path` returns a temporary file: RPC streams it and deletes it."""


def refusals() -> dict[str, tuple[type[Exception], int]]:
    """
    The service errors whose message is meant for the user, by class name, with the status
    each is sent as. Everything else is a bug or holds something private, such as a path,
    and reaches a thin client as a bare 500. Imported on first use: a thin client loads this
    module and has no use for the services' own modules until it sees one of these.
    """
    from chronicler.core.formatting import NoRealTimestampsError
    from chronicler.core.processing.regex_guard import PatternTimeoutError, UnsafePatternError

    return {
        "LookupError": (LookupError, 404),
        "NoRealTimestampsError": (NoRealTimestampsError, 422),
        "UnsafePatternError": (UnsafePatternError, 422),
        "PatternTimeoutError": (PatternTimeoutError, 422),
    }


def refusal_for(error: Exception) -> tuple[str, int] | None:
    """The class name and status `error` is sent as, or None if it is not one to explain."""
    # KeyError and IndexError are LookupErrors too, but their text is a bare key.
    if isinstance(error, KeyError | IndexError):
        return None
    for name, (cls, status_code) in refusals().items():
        if isinstance(error, cls):
            return name, status_code
    return None


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


class _UploadGuard:
    """
    ASGI middleware that checks an upload's API key before reading its body, then stops
    it at the cap while it is being received.

    FastAPI reads and spools a multipart body to a temporary file before it runs the
    endpoint's dependencies, the API key check included, so without this anyone who can
    reach the port could make the server write up to the cap to disk per request. And a
    check inside `/upload` limits what is kept, not what is received. This refuses a
    missing or wrong key, and a declared `Content-Length` over the limit, before reading
    anything, and counts the bytes that actually arrive for a client that lies about the
    length or sends none. See docs/security.md.
    """

    def __init__(self, app: Any, path: str, limit: Callable[[], int], api_key: Callable[[], str]):
        self.app = app
        self.path = path
        self.limit = limit
        self.api_key = api_key

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return

        from fastapi import HTTPException, status
        from starlette.responses import JSONResponse

        headers = dict(scope["headers"])
        # The same answers FastAPI's own check gives, before a byte of the body is read.
        given = headers.get(b"x-api-key")
        if given is None:
            refusal = JSONResponse({"detail": "Not authenticated"}, status_code=401)
        elif not secrets.compare_digest(given, self.api_key().encode()):
            refusal = JSONResponse({"detail": "Could not validate credentials"}, status_code=403)
        else:
            refusal = None
        if refusal is not None:
            await refusal(scope, receive, send)
            return

        limit = self.limit()
        detail = f"Upload exceeds the maximum of {limit} bytes"
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            response = JSONResponse({"detail": detail}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # FastAPI passes an HTTPException raised while parsing the body
                    # through as it is, so parsing stops here with a 413.
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=detail)
            return message

        await self.app(scope, counting_receive, send)


class RpcServer:
    MAX_UPLOAD_SIZE = 500 * 1024 * 1024
    UPLOAD_CHUNK_SIZE = 1024 * 1024
    # Room for the multipart boundary and part headers around the file itself. The
    # endpoint still holds the file to MAX_UPLOAD_SIZE exactly.
    MULTIPART_OVERHEAD = 64 * 1024

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
        from fastapi import Body, HTTPException, Response
        from fastapi.responses import FileResponse
        from sqlalchemy.ext.asyncio import AsyncSession
        from starlette.background import BackgroundTask

        sig = inspect.signature(method)
        returns_binary = method.__annotations__.get("return") in BINARY_RETURNS
        returns_file = method.__annotations__.get("return") is FILE_RETURN

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
                result = await bound_method(*args, **kwargs)
            except Exception as error:
                refusal = refusal_for(error)
                if refusal is None:
                    raise
                error_name, status_code = refusal
                raise HTTPException(
                    status_code, detail={"error": error_name, "message": str(error)}
                ) from error
            finally:
                if scope.is_registered(AsyncSession):
                    await scope.resolve(AsyncSession).close()

            if returns_binary:
                return Response(content=bytes(result), media_type=BINARY_MEDIA_TYPE)
            if returns_file:
                # Streamed from disk, then removed: the file was made for this one answer.
                return FileResponse(
                    result,
                    media_type=BINARY_MEDIA_TYPE,
                    background=BackgroundTask(lambda: Path(result).unlink(missing_ok=True)),
                )
            return result

        wrapper.__signature__ = new_sig  # type: ignore
        wrapper.__name__ = name
        wrapper.__annotations__ = dict(method.__annotations__)

        if returns_binary or returns_file:
            # A document is returned as it is, so the return annotation has to go with it:
            # left in place FastAPI builds a response model from it and refuses `bytearray`
            # outright. Every other route keeps its inferred model.
            wrapper.__annotations__.pop("return", None)
            router.add_api_route(f"/{name}", wrapper, methods=["POST"], response_model=None)
            return

        router.add_api_route(f"/{name}", wrapper, methods=["POST"])

    def build(self):
        from fastapi import Depends, FastAPI, File, HTTPException, Security, UploadFile, status
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
            _UploadGuard,
            path="/upload",
            limit=lambda: self.MAX_UPLOAD_SIZE + self.MULTIPART_OVERHEAD,
            api_key=lambda: self.api_key,
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
