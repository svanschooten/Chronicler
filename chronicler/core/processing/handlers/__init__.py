"""Task handlers, one module per TaskType."""

from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.processing.handlers.cleaning import CleanHandler
from chronicler.core.processing.handlers.importing import ImportHandler
from chronicler.core.processing.handlers.normalizing import NormalizeHandler
from chronicler.core.processing.handlers.summarizing import SummarizeHandler
from chronicler.core.processing.handlers.transcribing import TranscribeHandler


class WorkerHandlers(ImportHandler, CleanHandler, TranscribeHandler, SummarizeHandler):
    """Every task handler on one object."""


__all__ = [
    "CleanHandler",
    "HandlerBase",
    "ImportHandler",
    "NormalizeHandler",
    "ProgressCallback",
    "SummarizeHandler",
    "TranscribeHandler",
    "WorkerHandlers",
]
