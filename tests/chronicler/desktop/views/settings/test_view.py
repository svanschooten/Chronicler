from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest
import yaml

from chronicler.core.config import CONFIG_FILE_ENV_VAR, Settings, get_settings
from chronicler.desktop.views.settings import SettingsView
from chronicler.i18n import set_locale


def _all_text(control) -> list[str]:
    """Every ft.Text value in a control tree, so assertions ignore exact nesting."""
    found = []
    if isinstance(control, ft.Text) and control.value:
        found.append(control.value)

    children = []
    content = getattr(control, "content", None)
    if content is not None:
        children.append(content)
    controls = getattr(control, "controls", None)
    if controls:
        children.extend(controls)

    for child in children:
        found.extend(_all_text(child))
    return found


def _inputs(view) -> dict[str, object]:
    """Every data-tagged input control, keyed by its settings path."""
    found: dict[str, object] = {}

    def walk(control):
        path = getattr(control, "data", None)
        if (
            isinstance(path, str)
            and "." in path
            and isinstance(control, ft.Dropdown | ft.TextField | ft.Switch)
        ):
            found[path] = control
        for child in [getattr(control, "content", None)] + list(
            getattr(control, "controls", None) or []
        ):
            if child is not None:
                walk(child)

    for control in view.controls:
        walk(control)
    return found


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "chronicler.yaml"
    path.write_text(yaml.dump({"dark_mode": True}))
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()
    set_locale("en")


@pytest.fixture
def view(config_file):
    built = SettingsView(Settings())
    built.show_snackbar = MagicMock()
    return built, config_file


class TestSections:
    def test_every_configurable_group_is_present(self, view):
        built, _ = view
        text = " ".join(_all_text(ft.Column(controls=built.controls)))

        for heading in ("Appearance", "Workspace", "Connection", "Transcription", "Cleaning"):
            assert heading in text

    def test_shows_the_real_workspace_path(self, config_file, tmp_path):
        settings = Settings(workspace_path=tmp_path / "ws")
        built = SettingsView(settings)

        assert str(tmp_path / "ws") in " ".join(_all_text(ft.Column(controls=built.controls)))

    def test_shows_thin_client_connection_info(self, config_file):
        settings = Settings(server_url="http://remote:8000")
        built = SettingsView(settings)
        text = " ".join(_all_text(ft.Column(controls=built.controls)))

        assert "http://remote:8000" in text
        assert "Thin Client" in text

    def test_shows_full_stack_connection_info(self, config_file, tmp_path):
        built = SettingsView(Settings(workspace_path=tmp_path))

        assert "Full Stack" in " ".join(_all_text(ft.Column(controls=built.controls)))


class TestControlsReflectSettings:
    def test_transcription_language_offers_auto(self, view):
        built, _ = view
        dropdown = _inputs(built)["transcription.language"]

        assert dropdown.value == "auto"
        assert "auto" in [option.key for option in dropdown.options]

    def test_transcription_language_offers_the_ui_locales(self, view):
        built, _ = view
        keys = [option.key for option in _inputs(built)["transcription.language"].options]

        assert {"en", "nl"} <= set(keys)

    def test_a_configured_language_is_preselected(self, config_file):
        settings = Settings()
        settings.transcription.language = "nl"
        built = SettingsView(settings)

        assert _inputs(built)["transcription.language"].value == "nl"

    def test_model_size_offers_the_known_sizes(self, view):
        built, _ = view
        keys = [option.key for option in _inputs(built)["transcription.model_size"].options]

        assert "base" in keys
        assert "large-v3" in keys

    def test_threshold_shows_the_current_value(self, view):
        built, _ = view

        assert _inputs(built)["transcription.no_speech_threshold"].value == "0.6"

    def test_hallucination_phrases_render_one_per_line(self, view):
        built, _ = view
        value = _inputs(built)["cleaning.hallucination_phrases"].value

        assert value.splitlines()[0] == "you"
        assert len(value.splitlines()) > 3

    def test_the_api_key_field_is_masked(self, view):
        built, _ = view

        assert _inputs(built)["llm.api_key"].password is True


class TestEditing:
    @pytest.mark.asyncio
    async def test_changing_the_language_persists_it(self, view):
        built, path = view

        await built.apply("transcription.language", "nl")

        assert yaml.safe_load(path.read_text())["transcription"]["language"] == "nl"
        built.show_snackbar.assert_called_once()

    @pytest.mark.asyncio
    async def test_changing_the_threshold_persists_it(self, view):
        built, path = view

        await built.apply("transcription.no_speech_threshold", "0.25")

        assert yaml.safe_load(path.read_text())["transcription"]["no_speech_threshold"] == 0.25

    @pytest.mark.asyncio
    async def test_editing_the_phrase_list_persists_it(self, view):
        built, path = view

        await built.apply("cleaning.hallucination_phrases", "eerste\ntweede")

        stored = yaml.safe_load(path.read_text())["cleaning"]["hallucination_phrases"]
        assert stored == ["eerste", "tweede"]

    @pytest.mark.asyncio
    async def test_an_invalid_value_is_rejected_and_not_saved(self, view):
        built, path = view

        applied = await built.apply("transcription.no_speech_threshold", "9")

        assert applied is False
        assert "transcription" not in (yaml.safe_load(path.read_text()) or {})

    @pytest.mark.asyncio
    async def test_an_unsafe_pattern_is_rejected(self, view):
        built, _ = view

        assert await built.apply("cleaning.strip_patterns", "(a+)+$") is False

    @pytest.mark.asyncio
    async def test_a_control_change_routes_through_apply(self, view):
        built, path = view
        dropdown = _inputs(built)["transcription.model_size"]
        dropdown.value = "small"

        await built._value_changed(MagicMock(control=dropdown))

        assert yaml.safe_load(path.read_text())["transcription"]["model_size"] == "small"

    @pytest.mark.asyncio
    async def test_restoring_defaults_persists_them(self, view):
        built, path = view
        await built.apply("cleaning.hallucination_phrases", "custom")

        await built.restore_defaults_clicked(MagicMock(control=MagicMock(data="cleaning")))

        stored = yaml.safe_load(path.read_text())["cleaning"]["hallucination_phrases"]
        assert stored != ["custom"]
        assert "you" in stored


class TestCallbacks:
    @pytest.mark.asyncio
    async def test_dark_mode_persists_and_notifies(self, view):
        built, path = view
        callback = AsyncMock()
        built.on_dark_mode_change = callback

        await built._dark_mode_changed(MagicMock(control=MagicMock(value=False)))

        assert yaml.safe_load(path.read_text())["dark_mode"] is False
        callback.assert_awaited_once_with(False)

    @pytest.mark.asyncio
    async def test_dark_mode_without_a_callback_still_saves(self, view):
        built, path = view

        await built._dark_mode_changed(MagicMock(control=MagicMock(value=False)))

        assert yaml.safe_load(path.read_text())["dark_mode"] is False

    @pytest.mark.asyncio
    async def test_changing_the_locale_switches_the_active_translation(self, view):
        built, path = view
        callback = AsyncMock()
        built.on_locale_change = callback

        await built._locale_changed(MagicMock(control=MagicMock(value="nl")))

        from chronicler.i18n import get_locale

        assert get_locale() == "nl"
        assert yaml.safe_load(path.read_text())["ui"]["locale"] == "nl"
        callback.assert_awaited_once_with("nl")


class TestWorkspacePicker:
    @pytest.mark.asyncio
    async def test_picking_a_folder_persists_it(self, view, tmp_path):
        built, path = view
        built.file_picker = MagicMock()
        built.file_picker.get_directory_path = AsyncMock(return_value=str(tmp_path / "new-ws"))

        await built.pick_workspace_clicked(MagicMock())

        assert yaml.safe_load(path.read_text())["workspace_path"] == str(tmp_path / "new-ws")

    @pytest.mark.asyncio
    async def test_cancelling_the_picker_changes_nothing(self, view):
        built, path = view
        built.file_picker = MagicMock()
        built.file_picker.get_directory_path = AsyncMock(return_value=None)

        await built.pick_workspace_clicked(MagicMock())

        assert yaml.safe_load(path.read_text()).get("workspace_path") is None

    @pytest.mark.asyncio
    async def test_without_a_picker_it_reports_rather_than_crashing(self, view):
        built, _ = view
        built.file_picker = None

        await built.pick_workspace_clicked(MagicMock())

        built.show_snackbar.assert_called_once()
