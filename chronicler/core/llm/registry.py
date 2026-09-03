"""Which models are actually available, discovered once and cached."""

import logging
import time

from chronicler.core.config_sections import LlmSettings
from chronicler.core.llm.client import LlmError, ModelInfo, build_client

logger = logging.getLogger(__name__)

CACHE_SECONDS = 300.0


class ModelRegistry:
    """
    Caches the provider's model list.

    Discovery is a network round trip, and the picker is opened far more often than the
    set of installed models changes - so it is fetched once at startup and refreshed only
    on demand or after the cache expires.
    """

    def __init__(self, settings: LlmSettings, cache_seconds: float = CACHE_SECONDS):
        self.settings = settings
        self.cache_seconds = cache_seconds
        self._models: list[ModelInfo] = []
        self._fetched_at: float | None = None
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _is_fresh(self) -> bool:
        if self._fetched_at is None:
            return False
        return (time.monotonic() - self._fetched_at) < self.cache_seconds

    async def list_models(self, refresh: bool = False) -> list[ModelInfo]:
        if not refresh and self._is_fresh():
            return self._models

        if not self.settings.is_configured:
            self._models = []
            self._last_error = None
            self._fetched_at = time.monotonic()
            return self._models

        try:
            self._models = await build_client(self.settings).list_models()
            self._last_error = None
        except LlmError as error:
            logger.warning(f"Could not list models: {error}")
            self._last_error = str(error)
            self._models = self._configured_fallback()

        self._fetched_at = time.monotonic()
        return self._models

    def _configured_fallback(self) -> list[ModelInfo]:
        """The explicitly configured model, so an unreachable listing endpoint is not fatal."""
        if self.settings.provider == "openai_compatible" and self.settings.model:
            return [ModelInfo(id=self.settings.model, provider="openai_compatible")]
        if self.settings.provider == "llama_cpp" and self.settings.model_path:
            return [
                ModelInfo(
                    id=self.settings.model_path,
                    provider="llama_cpp",
                    label=self.settings.model_path.rsplit("/", 1)[-1],
                )
            ]
        return []

    async def model_ids(self, refresh: bool = False) -> list[str]:
        return [model.id for model in await self.list_models(refresh=refresh)]
