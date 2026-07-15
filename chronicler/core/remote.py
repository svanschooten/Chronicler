import inspect
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

import httpx
from pydantic import TypeAdapter

T = TypeVar("T")


class RemoteServiceProxy:
    def __init__(
        self,
        base_url: str,
        cls: type,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
    ):
        self._base_url = base_url
        self._cls = cls
        self._client = client or httpx.AsyncClient()
        self._api_key = api_key

        service_name = cls.__name__
        if service_name.endswith("Service"):
            self._prefix = service_name[:-7].lower()
        else:
            self._prefix = service_name.lower()

        for name, method in inspect.getmembers(cls, inspect.iscoroutinefunction):
            if name.startswith("_"):
                continue
            setattr(self, name, self._make_remote_method(name, method))

    def _make_remote_method(self, name: str, method: Callable):
        async def remote_method(*args, **kwargs):
            sig = inspect.signature(method)
            # Map args to their names
            bound_args = sig.bind(None, *args, **kwargs)  # 'None' for self
            payload = {k: v for k, v in bound_args.arguments.items() if k != "self"}

            # Serialize payload: Pydantic models in payload need to be converted to dicts
            # FastAPI handles this on server side, but httpx needs dicts/json.
            # We can use TypeAdapter to serialize the whole payload if we had a model for it,
            # but for now let's just use a simple approach.
            json_payload = {}
            for k, v in payload.items():
                if hasattr(v, "model_dump"):
                    json_payload[k] = v.model_dump()
                else:
                    json_payload[k] = v

            url = f"{self._base_url}/{self._prefix}/{name}"
            headers = {}
            if self._api_key:
                headers["X-API-Key"] = self._api_key

            response = await self._client.post(url, json=json_payload, headers=headers)
            response.raise_for_status()

            data = response.json()

            # Deserialize response
            hints = get_type_hints(method)
            return_type = hints.get("return")

            if return_type:
                # TypeAdapter can handle list[Model], Model | None, etc.
                return TypeAdapter(return_type).validate_python(data)

            return data

        return remote_method


class RemoteContainer:
    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
    ):
        self._base_url = base_url
        self._client = client
        self._api_key = api_key
        self._instances: dict[type, Any] = {}

    def resolve(self, cls: type[T]) -> T:
        if cls not in self._instances:
            self._instances[cls] = RemoteServiceProxy(
                self._base_url, cls, self._client, self._api_key
            )
        return self._instances[cls]  # type: ignore
