"""Task handlers, one module per TaskType.

`WorkerHandlers` is the single object both entry points (DesktopApp and the server)
register every handler from - see `build_worker_runtime` in
`chronicler.core.worker_wiring`, which is what actually maps TaskType to the methods
below.
"""

from chronicler.core.processing.handlers.base import HandlerBase, ProgressCallback
from chronicler.core.processing.handlers.cleaning import CleanHandler
from chronicler.core.processing.handlers.importing import ImportHandler
from chronicler.core.processing.handlers.transcribing import TranscribeHandler


class WorkerHandlers(ImportHandler, CleanHandler, TranscribeHandler):
    """Every task handler on one object.

    Composed by inheritance rather than delegation so the handlers keep sharing a
    single `db_manager`/`chronicle_repo` pair (and therefore one archive session) with
    no forwarding boilerplate. The three handler classes are independent - they define
    disjoint `handle_*` methods and share only `HandlerBase`.
    """


__all__ = [
    "CleanHandler",
    "HandlerBase",
    "ImportHandler",
    "ProgressCallback",
    "TranscribeHandler",
    "WorkerHandlers",
]
