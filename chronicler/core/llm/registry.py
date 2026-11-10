"""Which models are actually available."""

import logging

from chronicler.core.config_sections import LlmSettings
from chronicler.core.llm.client import LlmError, build_client
from chronicler.core.models import ModelCheck

logger = logging.getLogger(__name__)


async def discover_models(settings: LlmSettings) -> ModelCheck:
    """
    Asks the provider what it offers. An unreachable listing endpoint is not fatal: the
    explicitly configured model is offered, with the reason attached.
    """
    if not settings.is_configured:
        return ModelCheck()

    try:
        models = await build_client(settings).list_models()
    except LlmError as error:
        logger.warning(f"Could not list models: {error}")
        return ModelCheck(models=_configured_fallback(settings), error=str(error))
    return ModelCheck(models=[model.id for model in models])


def _configured_fallback(settings: LlmSettings) -> list[str]:
    if settings.provider == "openai_compatible" and settings.model:
        return [settings.model]
    if settings.provider == "llama_cpp" and settings.model_path:
        return [settings.model_path]
    return []
