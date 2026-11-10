from dataclasses import dataclass

import httpx

from chronicler.core.config import Mode, Settings
from chronicler.core.container import Container
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import FileStager, LocalFileStager, RemoteFileStager
from chronicler.core.local_container import register_local_repositories
from chronicler.core.remote import RPC_TIMEOUT, RemoteContainer
from chronicler.i18n import set_locale


@dataclass
class DesktopRuntime:
    """
    Everything DesktopApp needs to run in either deployment mode, built once at startup from
    Settings.
    """

    resolver: Container | RemoteContainer
    db_manager: DatabaseManager | None
    file_stager: FileStager
    settings: Settings
    http_client: httpx.AsyncClient | None = None


def build_runtime(settings: Settings) -> DesktopRuntime:
    set_locale(settings.ui.locale)

    if settings.desktop_mode is Mode.THIN_CLIENT:
        if not settings.server_url:
            raise ValueError("thin_client mode requires settings.server_url")
        http_client = httpx.AsyncClient(timeout=RPC_TIMEOUT)
        resolver: Container | RemoteContainer = RemoteContainer(
            settings.server_url, client=http_client, api_key=settings.api_key
        )
        remote_stager: FileStager = RemoteFileStager(
            settings.server_url, settings.api_key, client=http_client
        )
        return DesktopRuntime(
            resolver=resolver,
            db_manager=None,
            file_stager=remote_stager,
            settings=settings,
            http_client=http_client,
        )

    if not settings.workspace_path:
        raise ValueError("full_stack mode requires settings.workspace_path")
    db_manager = DatabaseManager(settings.workspace_path)
    container = Container()
    register_local_repositories(container, db_manager)
    local_stager: FileStager = LocalFileStager(db_manager.get_imports_path())
    return DesktopRuntime(
        resolver=container, db_manager=db_manager, file_stager=local_stager, settings=settings
    )
