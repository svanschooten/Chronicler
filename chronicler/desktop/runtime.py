from collections.abc import Callable
from dataclasses import dataclass

import httpx

from chronicler.core.config import Mode, Settings
from chronicler.core.database_manager import DatabaseManager
from chronicler.core.file_staging import FileStager, LocalFileStager, RemoteFileStager
from chronicler.core.remote import RPC_TIMEOUT
from chronicler.core.services.services import Services, local_services, remote_services
from chronicler.i18n import set_locale


@dataclass
class DesktopRuntime:
    """
    Everything DesktopApp needs to run in either deployment mode, built once at startup from
    Settings. `new_services` makes one set of services per view; the caller closes it.
    """

    new_services: Callable[[], Services]
    db_manager: DatabaseManager | None
    file_stager: FileStager
    settings: Settings
    http_client: httpx.AsyncClient | None = None


def build_runtime(settings: Settings) -> DesktopRuntime:
    set_locale(settings.ui.locale)

    if settings.desktop_mode is Mode.THIN_CLIENT:
        if not settings.server_url:
            raise ValueError("thin_client mode requires settings.server_url")
        url = settings.server_url
        http_client = httpx.AsyncClient(timeout=RPC_TIMEOUT)
        remote_stager: FileStager = RemoteFileStager(url, settings.api_key, client=http_client)
        return DesktopRuntime(
            new_services=lambda: remote_services(url, settings.api_key, http_client),
            db_manager=None,
            file_stager=remote_stager,
            settings=settings,
            http_client=http_client,
        )

    if not settings.workspace_path:
        raise ValueError("full_stack mode requires settings.workspace_path")
    db_manager = DatabaseManager(settings.workspace_path)
    local_stager: FileStager = LocalFileStager(db_manager.get_imports_path())
    return DesktopRuntime(
        new_services=lambda: local_services(db_manager, settings),
        db_manager=db_manager,
        file_stager=local_stager,
        settings=settings,
    )
