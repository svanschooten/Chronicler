import pytest

from chronicler.core.config import Mode, Settings
from chronicler.core.container import Container
from chronicler.core.file_staging import LocalFileStager, RemoteFileStager
from chronicler.core.remote import RemoteContainer
from chronicler.desktop.runtime import build_runtime


def test_full_stack_settings_build_a_local_container(tmp_path):
    settings = Settings(workspace_path=tmp_path, mode=Mode.FULL_STACK)
    runtime = build_runtime(settings)

    assert isinstance(runtime.resolver, Container)
    assert runtime.db_manager is not None
    assert isinstance(runtime.file_stager, LocalFileStager)


def test_thin_client_settings_build_a_remote_container():
    settings = Settings(server_url="http://example.invalid", api_key="key", mode=Mode.THIN_CLIENT)
    runtime = build_runtime(settings)

    assert isinstance(runtime.resolver, RemoteContainer)
    assert runtime.db_manager is None
    assert isinstance(runtime.file_stager, RemoteFileStager)


def test_missing_mode_infers_thin_client_from_server_url_only(tmp_path):
    """
    Configs saved before Settings.mode existed - inferred the same way desktop/main.py used
    to, rather than forcing a wizard re-run.
    """
    settings = Settings(
        server_url="http://example.invalid", api_key="key", mode=None, workspace_path=None
    )
    runtime = build_runtime(settings)

    assert isinstance(runtime.resolver, RemoteContainer)


def test_missing_mode_infers_full_stack_from_workspace_path(tmp_path):
    settings = Settings(workspace_path=tmp_path, mode=None)
    runtime = build_runtime(settings)

    assert isinstance(runtime.resolver, Container)


def test_thin_client_without_server_url_raises():
    settings = Settings(mode=Mode.THIN_CLIENT, server_url=None)
    with pytest.raises(ValueError, match="server_url"):
        build_runtime(settings)


def test_full_stack_without_workspace_path_raises():
    settings = Settings(mode=Mode.FULL_STACK, workspace_path=None)
    with pytest.raises(ValueError, match="workspace_path"):
        build_runtime(settings)


def test_build_runtime_activates_the_configured_locale(tmp_path):
    from chronicler.i18n import get_locale, set_locale

    workspace = tmp_path / "ws"
    workspace.mkdir()
    settings = Settings(workspace_path=workspace, mode=Mode.FULL_STACK)
    settings.ui.locale = "nl"
    try:
        build_runtime(settings)
        assert get_locale() == "nl"
    finally:
        set_locale("en")


def test_a_web_client_config_starts_as_a_thin_client():
    """Ticket 026: `client:web` with a server URL used to crash `build_runtime`."""
    settings = Settings(server_url="http://example.invalid", api_key="key", mode="client:web")

    runtime = build_runtime(settings)

    assert isinstance(runtime.resolver, RemoteContainer)


@pytest.mark.asyncio
async def test_thin_client_shares_one_long_timeout_client():
    settings = Settings(server_url="http://example.invalid", api_key="key", mode=Mode.THIN_CLIENT)
    runtime = build_runtime(settings)
    client = runtime.http_client

    assert client is not None
    assert client.timeout.connect == 10
    assert client.timeout.read == 600
    assert client.timeout.write == 600
    assert runtime.file_stager._client is client
    assert runtime.resolver._client is client
    await client.aclose()


def test_fallback_clients_use_the_long_timeouts():
    from chronicler.core.remote import RPC_TIMEOUT, RemoteServiceProxy

    proxy = RemoteServiceProxy("http://x", Settings)
    assert proxy._client.timeout == RPC_TIMEOUT


@pytest.mark.parametrize("mode", [None, *Mode])
@pytest.mark.parametrize("server_url", [None, "http://example.invalid"])
@pytest.mark.parametrize("has_workspace", [False, True])
@pytest.mark.parametrize("api_key", [None, "key"])
def test_validation_and_build_runtime_agree(tmp_path, mode, server_url, has_workspace, api_key):
    """Settings that validate for the desktop always build, as the mode validation named."""
    settings = Settings(
        mode=mode,
        server_url=server_url,
        workspace_path=tmp_path if has_workspace else None,
        api_key=api_key,
    )
    if not settings.validate_for_mode(settings.desktop_mode):
        return

    runtime = build_runtime(settings)

    thin = settings.desktop_mode is Mode.THIN_CLIENT
    assert isinstance(runtime.resolver, RemoteContainer if thin else Container)
