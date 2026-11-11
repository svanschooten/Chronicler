"""`chronicler server` is configured with flags or the environment, and never needs a terminal."""

import pytest

from chronicler.core.config import Mode, Settings
from chronicler.core.wizard import SetupError, configure_server


@pytest.fixture(autouse=True)
def _isolated(isolated_config):
    """Every test builds a Settings and saves it; see the shared fixture in conftest."""


def _fail_if_asked(_prompt: str) -> str:
    raise AssertionError("the server must not prompt when it was given everything")


def test_flags_configure_the_server_without_a_terminal(tmp_path):
    settings = Settings()
    said: list[str] = []

    configure_server(
        settings,
        workspace=str(tmp_path / "ws"),
        api_key="secret",
        interactive=False,
        ask=_fail_if_asked,
        say=said.append,
    )

    saved = Settings()
    assert saved.workspace_path == tmp_path / "ws"
    assert saved.api_key == "secret"
    assert saved.mode is Mode.SERVER
    assert not any("secret" in line for line in said)  # a key you gave is not echoed back


def test_a_missing_key_is_generated_and_printed_once(tmp_path):
    said: list[str] = []

    configure_server(Settings(), workspace=str(tmp_path), interactive=False, say=said.append)

    key = Settings().api_key
    assert key and len(key) >= 32
    assert sum(key in line for line in said) == 1


def test_without_a_terminal_a_missing_workspace_names_the_flag():
    with pytest.raises(SetupError, match="--workspace PATH.*CHRONICLER_WORKSPACE_PATH"):
        configure_server(Settings(), interactive=False, ask=_fail_if_asked)


def test_with_a_terminal_a_missing_workspace_is_asked_for(tmp_path):
    answers = iter([str(tmp_path / "typed")])

    configure_server(
        Settings(), api_key="k", interactive=True, ask=lambda _p: next(answers), say=lambda _l: None
    )

    assert Settings().workspace_path == tmp_path / "typed"


def test_an_empty_answer_takes_the_default_workspace(tmp_path, monkeypatch):
    from chronicler.core import wizard

    monkeypatch.setattr(wizard, "default_workspace_path", lambda: tmp_path / "Default")

    configure_server(
        Settings(), api_key="k", interactive=True, ask=lambda _p: "", say=lambda _l: None
    )

    assert Settings().workspace_path == tmp_path / "Default"


def test_a_configuration_that_is_already_complete_is_left_alone(tmp_path):
    settings = Settings(workspace_path=tmp_path, api_key="k", mode=Mode.SERVER)

    changed = configure_server(settings, interactive=False, ask=_fail_if_asked)

    assert changed is False


def test_a_workspace_that_cannot_be_written_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "is_workspace_valid", lambda self: False)

    with pytest.raises(SetupError, match="cannot write"):
        configure_server(Settings(), workspace=str(tmp_path), api_key="k", interactive=False)


def test_the_environment_alone_is_enough(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLER_WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("CHRONICLER_API_KEY", "from-env")

    settings = Settings()
    configure_server(settings, interactive=False, ask=_fail_if_asked, say=lambda _l: None)

    assert settings.workspace_path == tmp_path
    assert settings.api_key == "from-env"
