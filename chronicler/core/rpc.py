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
        from fastapi import Depends, FastAPI, HTTPException, Security, status
        from fastapi.security import APIKeyHeader

        api_key_header = APIKeyHeader(name="X-API-Key")

        async def verify_api_key(api_key: str = Security(api_key_header)):
            if api_key != self.api_key:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Could not validate credentials",
                )
            return api_key

        self._app = FastAPI(
            title="Chronicler RPC Server",
            dependencies=[Depends(verify_api_key)],
        )

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
