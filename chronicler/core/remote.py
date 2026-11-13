import inspect
import os
import tempfile
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

import httpx
from pydantic import TypeAdapter

from chronicler.core.rpc import BINARY_RETURNS, FILE_RETURN, TempFile, exposed_methods, refusals

T = TypeVar("T")

# The server builds a zip or PDF before sending its first byte, so reads and writes need
# minutes, not httpx's 5-second default.
RPC_TIMEOUT = httpx.Timeout(10, read=600, write=600)


def _raise_refusal(response: httpx.Response) -> None:
    """
    Raises the service's own exception when the server refused with one it explains, so
    `str(error)` and an `except` clause read the same as against a local service.
    """
    if response.status_code not in (404, 422):
        return
    try:
        detail = response.json()["detail"]
        known = refusals()[detail["error"]][0]
        message = detail["message"]
    except (ValueError, KeyError, TypeError):
        return  # a 404 for a missing route, or a validation error: not one of ours
    raise known(message)


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
        self._client = client or httpx.AsyncClient(timeout=RPC_TIMEOUT)
        self._api_key = api_key

        service_name = cls.__name__
        if service_name.endswith("Service"):
            self._prefix = service_name[:-7].lower()
        else:
            self._prefix = service_name.lower()

        for name in exposed_methods(cls):
            setattr(self, name, self._make_remote_method(name, getattr(cls, name)))

    async def _download(self, url: str, payload: dict, headers: dict) -> TempFile:
        """
        Streams the answer into a temporary file, which the caller owns. It goes to the
        system's temporary directory, readable only by its owner, since a thin client has no
        workspace of its own.
        """
        async with self._client.stream("POST", url, json=payload, headers=headers) as response:
            if not response.is_success:
                await response.aread()
                _raise_refusal(response)
                response.raise_for_status()

            handle, name = tempfile.mkstemp(prefix="chronicler-", suffix=".download")
            path = TempFile(name)
            try:
                with os.fdopen(handle, "wb") as out:
                    async for chunk in response.aiter_bytes():
                        out.write(chunk)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        return path

    def _make_remote_method(self, name: str, method: Callable):
        sig = inspect.signature(method)
        param_hints = get_type_hints(method)

        async def remote_method(*args, **kwargs):
            bound_args = sig.bind(None, *args, **kwargs)
            payload = {k: v for k, v in bound_args.arguments.items() if k != "self"}

            json_payload = {}
            for k, v in payload.items():
                param_type = param_hints.get(k)
                if param_type is not None:
                    json_payload[k] = TypeAdapter(param_type).dump_python(v, mode="json")
                elif hasattr(v, "model_dump"):
                    json_payload[k] = v.model_dump()
                else:
                    json_payload[k] = v

            url = f"{self._base_url}/{self._prefix}/{name}"
            headers = {}
            if self._api_key:
                headers["X-API-Key"] = self._api_key

            return_type = param_hints.get("return")

            if return_type is FILE_RETURN:
                return await self._download(url, json_payload, headers)

            response = await self._client.post(url, json=json_payload, headers=headers)
            _raise_refusal(response)
            response.raise_for_status()

            if return_type in BINARY_RETURNS:
                return bytearray(response.content)

            data = response.json()

            if return_type:
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
