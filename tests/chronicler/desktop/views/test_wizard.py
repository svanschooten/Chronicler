"""The desktop setup wizard, driven the way a user clicks through it."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import flet as ft
import pytest

from chronicler.core.config import Settings
from chronicler.desktop.views.wizard import FULL_STACK, THIN_CLIENT, FletSetupWizard
from chronicler.i18n import set_locale, t
from tests.chronicler.desktop.controls import find_controls, text_values

BUTTONS = (ft.FilledButton, ft.TextButton, ft.OutlinedButton)


@pytest.fixture(autouse=True)
def reset_locale():
    yield
    set_locale("en")


@pytest.fixture
def wizard(isolated_config):
    """A wizard sitting on its first step, as `run()` leaves it."""
    page = MagicMock()
    page.services = []
    wizard = FletSetupWizard(page, Settings())
    wizard.show_language()
    return wizard


# -- driving the tree ---------------------------------------------------------


def click(wizard, label: str) -> None:
    """Presses the button on the current step whose label is `label`."""
    matches = find_controls(
        wizard._root,
        lambda control: isinstance(control, BUTTONS) and control.content == label,
    )
    assert matches, f"no button labelled {label!r} on this step, found: {_button_labels(wizard)}"
    matches[0].on_click(None)


def choose(wizard, label: str) -> None:
    """Clicks the mode card whose heading is `label`."""
    cards = find_controls(
        wizard._root,
        lambda control: isinstance(control, ft.Container) and control.on_click is not None,
    )
    for card in cards:
        if label in text_values(card):
            card.on_click(None)
            return
    raise AssertionError(f"no choice card labelled {label!r}")


def fields(wizard) -> list[ft.TextField]:
    return find_controls(wizard._root, lambda control: isinstance(control, ft.TextField))


def dropdown(wizard) -> ft.Dropdown:
    return find_controls(wizard._root, lambda control: isinstance(control, ft.Dropdown))[0]


def _button_labels(wizard) -> list:
    return [
        control.content for control in find_controls(wizard._root, lambda c: isinstance(c, BUTTONS))
    ]


def pick_language(wizard, code: str = "en") -> None:
    dropdown(wizard).value = code
    click(wizard, t("wizard.next"))


# -- happy paths --------------------------------------------------------------


def test_full_stack_run_writes_a_complete_configuration(wizard, tmp_path):
    workspace = tmp_path / "workspace"

    pick_language(wizard, "en")
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(workspace)
    click(wizard, t("wizard.next"))
    generated = fields(wizard)[0].value
    click(wizard, t("wizard.finish"))

    saved = Settings()
    assert saved.mode == FULL_STACK
    assert saved.workspace_path == workspace
    assert saved.server_url is None
    assert saved.api_key == generated
    assert saved.ui.locale == "en"
    assert saved.transcription.language == "en"


def test_thin_client_run_writes_a_complete_configuration(wizard):
    pick_language(wizard, "en")
    choose(wizard, t("wizard.mode.thin_client"))
    url_field, key_field = fields(wizard)
    url_field.value = "http://remote:8000"
    key_field.value = "the-server-key"
    click(wizard, t("wizard.finish"))

    saved = Settings()
    assert saved.mode == THIN_CLIENT
    assert saved.server_url == "http://remote:8000"
    assert saved.api_key == "the-server-key"
    assert saved.workspace_path is None


@pytest.mark.asyncio
async def test_finishing_releases_run(wizard, tmp_path):
    """`run()` is what the caller awaits before it builds the runtime."""
    task = asyncio.ensure_future(wizard.run())
    await asyncio.sleep(0)
    assert not task.done()

    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))
    click(wizard, t("wizard.finish"))

    await asyncio.wait_for(task, timeout=1)
    assert Settings().workspace_path == tmp_path / "workspace"


# -- language -----------------------------------------------------------------


def test_the_language_step_relabels_the_rest_of_the_wizard(wizard):
    """
    Language is asked first precisely so everything after it is in the user's own language -
    the wizard rebuilds from `t()` on every step rather than updating labels in place.
    """
    pick_language(wizard, "nl")

    set_locale("nl")
    assert t("wizard.mode.title") in text_values(wizard._root)
    set_locale("en")
    assert t("wizard.mode.title") not in text_values(wizard._root)


def test_the_chosen_language_becomes_the_transcription_default(wizard, tmp_path):
    pick_language(wizard, "de")
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))
    click(wizard, t("wizard.finish"))

    saved = Settings()
    assert saved.ui.locale == "de"
    assert saved.transcription.language == "de"


# -- validation ---------------------------------------------------------------


def test_an_empty_workspace_path_is_refused(wizard):
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    field = fields(wizard)[0]
    field.value = "   "
    click(wizard, t("wizard.next"))

    assert field.error == t("wizard.workspace.required")
    assert wizard.workspace_path is None


def test_the_remote_step_requires_both_a_url_and_a_key(wizard):
    """
    The key has to match one the server operator already set, so unlike the full-stack step
    it cannot be generated here - leaving it blank would guarantee a 403 on every request.
    """
    pick_language(wizard)
    choose(wizard, t("wizard.mode.thin_client"))
    url_field, key_field = fields(wizard)
    url_field.value = "http://remote:8000"
    key_field.value = ""
    click(wizard, t("wizard.finish"))

    assert url_field.error is None
    assert key_field.error == t("wizard.server.key_required")
    assert wizard.api_key is None
    assert t("wizard.server.title") in text_values(wizard._root), "it must not have advanced"


# -- api key ------------------------------------------------------------------


def test_the_api_key_step_offers_a_generated_key(wizard, tmp_path):
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))

    assert len(fields(wizard)[0].value) == 43


def test_regenerating_replaces_the_offered_key(wizard, tmp_path):
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))

    first = fields(wizard)[0].value
    click(wizard, t("wizard.api_key.generate"))

    assert fields(wizard)[0].value != first


def test_skipping_the_api_key_leaves_remote_access_off(wizard, tmp_path):
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))
    click(wizard, t("wizard.api_key.skip"))

    saved = Settings()
    assert saved.api_key is None
    assert saved.workspace_path == tmp_path / "workspace"


# -- navigation ---------------------------------------------------------------


def test_back_returns_to_the_previous_step(wizard, tmp_path):
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))

    click(wizard, t("wizard.back"))
    assert t("wizard.workspace.title") in text_values(wizard._root)

    click(wizard, t("wizard.back"))
    assert t("wizard.mode.title") in text_values(wizard._root)


def test_the_step_counter_shortens_for_the_thin_client(wizard):
    """Thin client asks for a server instead of a workspace *and* a key."""
    pick_language(wizard)
    choose(wizard, t("wizard.mode.thin_client"))

    assert t("wizard.step", number=3, total=3) in text_values(wizard._root)


# -- switching mode after entering details ------------------------------------


def test_switching_to_thin_client_clears_the_workspace(wizard, tmp_path):
    """
    A config carrying both a workspace and a server URL is ambiguous - build_runtime()
    picks full stack whenever a workspace is set, silently ignoring the server.
    """
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))
    click(wizard, t("wizard.back"))
    click(wizard, t("wizard.back"))

    choose(wizard, t("wizard.mode.thin_client"))
    url_field, key_field = fields(wizard)
    url_field.value = "http://remote:8000"
    key_field.value = "key"
    click(wizard, t("wizard.finish"))

    saved = Settings()
    assert saved.workspace_path is None
    assert saved.server_url == "http://remote:8000"


# -- the folder picker --------------------------------------------------------


@pytest.mark.asyncio
async def test_browsing_fills_the_workspace_field(wizard, tmp_path):
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))

    wizard.picker.pick_directory = _returning(str(tmp_path / "picked"))
    browse = find_controls(
        wizard._root,
        lambda control: (
            isinstance(control, ft.OutlinedButton)
            and control.content == t("wizard.workspace.browse")
        ),
    )[0]
    await browse.on_click(None)

    assert fields(wizard)[0].value == str(tmp_path / "picked")


@pytest.mark.asyncio
async def test_a_cancelled_browse_leaves_the_field_alone(wizard):
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))

    before = fields(wizard)[0].value
    wizard.picker.pick_directory = _returning(None)
    browse = find_controls(
        wizard._root,
        lambda control: (
            isinstance(control, ft.OutlinedButton)
            and control.content == t("wizard.workspace.browse")
        ),
    )[0]
    await browse.on_click(None)

    assert fields(wizard)[0].value == before


def _returning(value):
    async def picker(_title):
        return value

    return picker


# -- theme --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dark_mode", "expected"),
    [(True, ft.ThemeMode.DARK), (False, ft.ThemeMode.LIGHT)],
)
def test_the_page_theme_follows_the_configured_workspace(isolated_config, dark_mode, expected):
    """
    Material paints the dropdown, fields and buttons from `page.theme_mode`, which defaults
    to following the OS - a dark workspace on a light desktop drew dark text on the dark
    card and was unreadable.
    """
    page = MagicMock()
    page.services = []
    wizard = FletSetupWizard(page, Settings(dark_mode=dark_mode))

    wizard.apply_theme()

    assert page.theme_mode is expected
    assert page.bgcolor == wizard.colors.surface


# -- registration -------------------------------------------------------------


def test_the_picker_is_registered_and_handed_back(wizard, tmp_path):
    """
    The folder dialog is a page service. Leaving it registered would strand a picker the
    wizard no longer owns in a page the archive and settings views register their own into.
    """
    wizard._ensure_picker()
    assert wizard.file_picker in wizard.page.services

    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = str(tmp_path / "workspace")
    click(wizard, t("wizard.next"))
    click(wizard, t("wizard.finish"))

    assert wizard.file_picker not in wizard.page.services


def test_existing_settings_prefill_the_steps(isolated_config):
    """Re-running after a half-finished setup should not make the user retype what is there."""
    page = MagicMock()
    page.services = []
    wizard = FletSetupWizard(page, Settings(server_url="http://remote:8000", ui={"locale": "nl"}))
    wizard.show_language()

    assert dropdown(wizard).value == "nl"

    pick_language(wizard, "nl")
    choose(wizard, t("wizard.mode.thin_client"))

    assert fields(wizard)[0].value == "http://remote:8000"


def test_the_default_workspace_is_offered(wizard):
    from chronicler.core.wizard import default_workspace_path

    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))

    assert fields(wizard)[0].value == str(default_workspace_path())


def test_a_relative_workspace_path_is_resolved(wizard, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    pick_language(wizard)
    choose(wizard, t("wizard.mode.full_stack"))
    fields(wizard)[0].value = "workspace"
    click(wizard, t("wizard.next"))

    assert wizard.workspace_path == Path(tmp_path / "workspace").resolve()
