"""Talking to a language model, wherever it runs."""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from chronicler.core import extras
from chronicler.core.config_sections import LlmSettings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300.0


class LlmError(RuntimeError):
    """The model could not be reached, or refused the request."""


class LlmNotConfiguredError(LlmError):
    """No provider is configured, so nothing can be generated."""


@dataclass(frozen=True)
class ModelInfo:
    id: str
    provider: str
    label: str | None = None


@dataclass
class Completion:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LlmClient(Protocol):
    """The one interface every provider is reached through."""

    async def list_models(self) -> list[ModelInfo]: ...

    async def complete(
        self, prompt: str, system: str | None = None, model: str | None = None, **options: Any
    ) -> Completion: ...


class OpenAiCompatibleClient:
    """
    Any server speaking the OpenAI chat-completions API.

    That covers llama.cpp's own server, Ollama, LM Studio, vLLM and hosted gateways, so
    "local model" and "remote model" differ only by configuration.
    """

    def __init__(self, settings: LlmSettings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.settings.base_url:
            raise LlmNotConfiguredError("No base_url configured for the language model")

        url = f"{self.settings.base_url}{path}"
        client = self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        try:
            response = await client.request(method, url, headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            raise LlmError(
                f"{error.response.status_code} from {url}: {error.response.text[:200]}"
            ) from error
        except httpx.HTTPError as error:
            raise LlmError(f"Could not reach {url}: {error}") from error
        finally:
            if self._client is None:
                await client.aclose()

    async def list_models(self) -> list[ModelInfo]:
        payload = await self._request("GET", "/models")
        entries = payload.get("data", payload if isinstance(payload, list) else [])
        return [
            ModelInfo(id=entry["id"], provider="openai_compatible")
            for entry in entries
            if isinstance(entry, dict) and entry.get("id")
        ]

    async def complete(
        self, prompt: str, system: str | None = None, model: str | None = None, **options: Any
    ) -> Completion:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model or self.settings.model,
            "messages": messages,
            "temperature": options.get("temperature", self.settings.temperature),
            "max_tokens": options.get("max_tokens", self.settings.max_tokens),
        }
        payload = await self._request("POST", "/chat/completions", json=body)

        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LlmError(f"Unexpected response shape from the model: {payload}") from error

        usage = payload.get("usage") or {}
        return Completion(
            text=text.strip(),
            model=payload.get("model") or body["model"] or "unknown",
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


class LlamaCppClient:
    """An in-process GGUF model, for running without any server at all."""

    def __init__(self, settings: LlmSettings):
        self.settings = settings
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.settings.model_path:
            raise LlmNotConfiguredError("No model_path configured for the local model")

        try:
            from llama_cpp import Llama
        except (ImportError, OSError) as error:
            raise LlmError(extras.missing_message("llm", error)) from error

        logger.info(f"Loading local model {self.settings.model_path} (downloads on first use)")
        self._model = Llama(
            model_path=self.settings.model_path, n_ctx=self.settings.context_window, verbose=False
        )
        return self._model

    async def list_models(self) -> list[ModelInfo]:
        if not self.settings.model_path:
            return []
        name = self.settings.model_path.rsplit("/", 1)[-1]
        return [ModelInfo(id=self.settings.model_path, provider="llama_cpp", label=name)]

    async def complete(
        self, prompt: str, system: str | None = None, model: str | None = None, **options: Any
    ) -> Completion:
        import asyncio

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        def run() -> Any:
            return self._load().create_chat_completion(
                messages=messages,
                temperature=options.get("temperature", self.settings.temperature),
                max_tokens=options.get("max_tokens", self.settings.max_tokens),
            )

        try:
            payload = await asyncio.to_thread(run)
        except LlmError:
            raise
        except Exception as error:
            raise LlmError(f"Local model failed: {error}") from error

        usage = payload.get("usage") or {}
        return Completion(
            text=payload["choices"][0]["message"]["content"].strip(),
            model=model or self.settings.model_path or "local",
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


def build_client(settings: LlmSettings, http_client: httpx.AsyncClient | None = None) -> LlmClient:
    """The client for the configured provider."""
    if settings.provider == "openai_compatible":
        return OpenAiCompatibleClient(settings, http_client)
    if settings.provider == "llama_cpp":
        return LlamaCppClient(settings)
    raise LlmNotConfiguredError(
        "No language model provider is configured. Set one in Settings > Language model."
    )
