import pytest

from chronicler.core.config import Settings
from chronicler.core.container import Container
from chronicler.core.file_staging import LocalFileStager, RemoteFileStager
from chronicler.core.remote import RemoteContainer
from chronicler.desktop.runtime import build_runtime


def test_full_stack_settings_build_a_local_container(tmp_path):
    settings = Settings(workspace_path=tmp_path, mode="desktop:full_stack")
    runtime = build_runtime(settings)

    assert isinstance(runtime.resolver, Container)
    assert runtime.db_manager is not None
    assert isinstance(runtime.file_stager, LocalFileStager)


def test_thin_client_settings_build_a_remote_container():
    settings = Settings(
        server_url="http://example.invalid", api_key="key", mode="desktop:thin_client"
    )
    runtime = build_runtime(settings)

    assert isinstance(runtime.resolver, RemoteContainer)
    assert runtime.db_manager is None
    assert isinstance(runtime.file_stager, RemoteFileStager)


def test_missing_mode_infers_thin_client_from_server_url_only(tmp_path):
    """Configs saved before Settings.mode existed - inferred the same way
    desktop/main.py used to, rather than forcing a wizard re-run."""
    # workspace_path explicitly None: Settings() otherwise falls back to whatever this
    # machine's real config file has, which would leak into the inference this test
    # targets.
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
    settings = Settings(mode="desktop:thin_client", server_url=None)
    with pytest.raises(ValueError, match="server_url"):
        build_runtime(settings)


def test_full_stack_without_workspace_path_raises():
    settings = Settings(mode="desktop:full_stack", workspace_path=None)
    with pytest.raises(ValueError, match="workspace_path"):
        build_runtime(settings)
