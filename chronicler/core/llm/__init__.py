"""Language model access, shared by every feature that needs generation."""

from chronicler.core.llm.client import (
    Completion,
    LlamaCppClient,
    LlmClient,
    LlmError,
    LlmNotConfiguredError,
    ModelInfo,
    OpenAiCompatibleClient,
    build_client,
)
from chronicler.core.llm.registry import discover_models

__all__ = [
    "Completion",
    "LlamaCppClient",
    "LlmClient",
    "LlmError",
    "LlmNotConfiguredError",
    "ModelInfo",
    "OpenAiCompatibleClient",
    "build_client",
    "discover_models",
]
