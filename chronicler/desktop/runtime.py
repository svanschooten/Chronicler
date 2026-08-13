from dataclasses import dataclass

from chronicler.core.config import Settings
from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import FileStager, LocalFileStager, RemoteFileStager
from chronicler.core.local_container import register_local_repositories
from chronicler.core.remote import RemoteContainer


@dataclass
class DesktopRuntime:
    """Everything DesktopApp needs to run in either deployment mode, built once at
    startup from Settings. `db_manager` is None in thin-client mode - there's no local
    workspace at all, and DesktopApp uses its presence to decide whether it owns a
    WorkerManager (thin client has no local tasks to run; the server it's pointed at
    runs its own, see server/main.py).
    """

    resolver: Container | RemoteContainer
    db_manager: DatabaseManager | None
    file_stager: FileStager
    settings: Settings


def build_runtime(settings: Settings) -> DesktopRuntime:
    mode = settings.mode
    if mode is None:
        # Configs saved before Settings.mode existed - infer the same way
        # desktop/main.py used to, rather than forcing a re-run of the wizard.
        mode = (
            "desktop:thin_client"
            if settings.server_url and not settings.workspace_path
            else "desktop:full_stack"
        )

    if mode == "desktop:thin_client":
        if not settings.server_url:
            raise ValueError("desktop:thin_client mode requires settings.server_url")
        resolver: Container | RemoteContainer = RemoteContainer(
            settings.server_url, api_key=settings.api_key
        )
        remote_stager: FileStager = RemoteFileStager(settings.server_url, settings.api_key)
        return DesktopRuntime(
            resolver=resolver, db_manager=None, file_stager=remote_stager, settings=settings
        )

    if not settings.workspace_path:
        raise ValueError("desktop:full_stack mode requires settings.workspace_path")
    db_manager = DatabaseManager(settings.workspace_path)
    container = Container()
    register_local_repositories(container, db_manager)
    local_stager: FileStager = LocalFileStager(db_manager.get_imports_path())
    return DesktopRuntime(
        resolver=container, db_manager=db_manager, file_stager=local_stager, settings=settings
    )
