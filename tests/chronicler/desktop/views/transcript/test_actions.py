"""Tests for the chronicle action row inside the transcript view."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.actions import ChronicleActionCallbacks, ChronicleActions
from tests.chronicler.desktop.controls import find_controls


@pytest.fixture
def make_actions():
    def _make(**overrides):
        chronicle = overrides.pop("chronicle", None) or Chronicle(id=uuid4(), title="Session One")
        parts = {
            "imports": AsyncMock(),
            "task_service": AsyncMock(),
            "transcript_service": AsyncMock(),
            "chronicle_service": AsyncMock(),
            "picker": AsyncMock(),
            "show_snackbar": MagicMock(),
            "callbacks": ChronicleActionCallbacks(
                on_changed=AsyncMock(), on_deleted=AsyncMock(), on_summarize=AsyncMock()
            ),
        }
        parts.update(overrides)
        row = ChronicleActions(
            chronicle,
            parts["imports"],
            parts["task_service"],
            parts["transcript_service"],
            parts["chronicle_service"],
            parts["picker"],
            theme_colors(True),
            parts["show_snackbar"],
            parts["callbacks"],
        )
        return row, parts, chronicle

    return _make


def _labels(row) -> list[str]:
    return [
        control.value
        for control in find_controls(row, lambda c: isinstance(c, ft.Text) and c.value)
    ]


class TestTheRow:
    def test_it_offers_every_chronicle_level_action(self, make_actions):
        row, _, _ = make_actions()

        tooltips = [
            c.tooltip or "" for c in find_controls(row, lambda c: getattr(c, "tooltip", None))
        ]
        shown = " ".join(_labels(row) + tooltips)
        for expected in ("Import audio", "Import transcript", "Clean", "speakers", "summary"):
            assert expected.lower() in shown.lower()

    def test_edit_and_delete_are_reachable_here_too(self, make_actions):
        row, _, _ = make_actions()

        tooltips = " ".join(
            c.tooltip or "" for c in find_controls(row, lambda c: getattr(c, "tooltip", None))
        )
        assert "Edit" in tooltips
        assert "Delete" in tooltips


class TestCleaning:
    @pytest.mark.asyncio
    async def test_it_queues_a_clean_task_for_this_chronicle(self, make_actions):
        row, parts, chronicle = make_actions()

        await row.clean_clicked(MagicMock())

        parts["task_service"].queue_clean.assert_awaited_once_with(chronicle.id)
        parts["show_snackbar"].assert_called_once()


class TestIdentifySpeakers:
    @pytest.mark.asyncio
    async def test_it_refreshes_the_count_and_reloads(self, make_actions):
        row, parts, chronicle = make_actions()
        parts["transcript_service"].refresh_speaker_count.return_value = 3

        await row.identify_speakers_clicked(MagicMock())

        parts["transcript_service"].refresh_speaker_count.assert_awaited_once_with(chronicle.id)
        parts["callbacks"].on_changed.assert_awaited_once()
        assert "3" in parts["show_snackbar"].call_args[0][0]


class TestSummarize:
    @pytest.mark.asyncio
    async def test_it_hands_off_to_the_summaries_panel(self, make_actions):
        row, parts, _ = make_actions()

        await row.summarize_clicked(MagicMock())

        parts["callbacks"].on_summarize.assert_awaited_once()


class TestImportingAudio:
    @pytest.mark.asyncio
    async def test_it_imports_into_this_chronicle(self, make_actions):
        row, parts, chronicle = make_actions()
        parts["picker"].pick_file.return_value = "/audio/alice.mp3"
        parts["imports"].import_audio.return_value = "Added alice.mp3"

        await row.import_audio_clicked(MagicMock())

        parts["imports"].import_audio.assert_awaited_once_with(chronicle.id, "/audio/alice.mp3")
        parts["callbacks"].on_changed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_it_only_offers_audio_extensions(self, make_actions):
        row, parts, _ = make_actions()
        parts["picker"].pick_file.return_value = None

        await row.import_audio_clicked(MagicMock())

        assert "mp3" in parts["picker"].pick_file.await_args[0][0]

    @pytest.mark.asyncio
    async def test_cancelling_the_picker_imports_nothing(self, make_actions):
        row, parts, _ = make_actions()
        parts["picker"].pick_file.return_value = None

        await row.import_audio_clicked(MagicMock())

        parts["imports"].import_audio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failing_import_is_reported_rather_than_raised(self, make_actions):
        row, parts, _ = make_actions()
        parts["picker"].pick_file.return_value = "/audio/alice.mp3"
        parts["imports"].import_audio.side_effect = RuntimeError("disk full")

        await row.import_audio_clicked(MagicMock())

        assert "disk full" in parts["show_snackbar"].call_args[0][0]


class TestImportingATranscript:
    @pytest.mark.asyncio
    async def test_the_regex_form_opens_first(self, make_actions, attach_page):
        row, _, _ = make_actions()
        page = attach_page(ChronicleActions)

        await row.import_transcript_clicked(MagicMock())

        assert row.transcript_form.dialog.open is True
        page.update.assert_called()

    @pytest.mark.asyncio
    async def test_confirming_the_form_picks_a_file_and_imports_it(self, make_actions, attach_page):
        row, parts, chronicle = make_actions()
        attach_page(ChronicleActions)
        parts["picker"].pick_file.return_value = "/t/session.txt"
        parts["imports"].import_transcript.return_value = "Queued"

        await row.transcript_import_confirmed(MagicMock())

        assert parts["imports"].import_transcript.await_args[0][0] == chronicle.id
        assert parts["imports"].import_transcript.await_args[0][1] == "/t/session.txt"

    @pytest.mark.asyncio
    async def test_cancelling_the_picker_after_the_form_imports_nothing(
        self, make_actions, attach_page
    ):
        row, parts, _ = make_actions()
        attach_page(ChronicleActions)
        parts["picker"].pick_file.return_value = None

        await row.transcript_import_confirmed(MagicMock())

        parts["imports"].import_transcript.assert_not_awaited()


class TestEditing:
    @pytest.mark.asyncio
    async def test_the_edit_form_opens_filled_from_the_chronicle(self, make_actions, attach_page):
        row, _, chronicle = make_actions()
        attach_page(ChronicleActions)

        await row.edit_clicked(MagicMock())

        assert row.edit_form.title_field.value == chronicle.title
        assert row.edit_form.dialog.open is True

    @pytest.mark.asyncio
    async def test_saving_writes_the_edits_and_reloads(self, make_actions, attach_page):
        row, parts, chronicle = make_actions()
        attach_page(ChronicleActions)
        parts["chronicle_service"].get_chronicle.return_value = chronicle

        await row.edit_clicked(MagicMock())
        row.edit_form.title_field.value = "Session One, cleaned"
        await row.edit_save_clicked(MagicMock())

        saved = parts["chronicle_service"].update_chronicle.await_args[0][0]
        assert saved.title == "Session One, cleaned"
        parts["callbacks"].on_changed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_saving_a_chronicle_that_vanished_reports_instead_of_crashing(
        self, make_actions, attach_page
    ):
        row, parts, _ = make_actions()
        attach_page(ChronicleActions)
        parts["chronicle_service"].get_chronicle.return_value = None

        await row.edit_save_clicked(MagicMock())

        parts["chronicle_service"].update_chronicle.assert_not_awaited()
        parts["show_snackbar"].assert_called_once()


class TestDeleting:
    @pytest.mark.asyncio
    async def test_it_confirms_before_deleting(self, make_actions, attach_page):
        row, parts, _ = make_actions()
        attach_page(ChronicleActions)

        with patch(
            "chronicler.desktop.views.transcript.actions.confirm",
            new=AsyncMock(return_value=False),
        ) as ask:
            await row.delete_clicked(MagicMock())

        ask.assert_awaited_once()
        parts["chronicle_service"].delete_chronicle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirming_deletes_and_leaves_the_view(self, make_actions, attach_page):
        row, parts, chronicle = make_actions()
        attach_page(ChronicleActions)

        with patch(
            "chronicler.desktop.views.transcript.actions.confirm",
            new=AsyncMock(return_value=True),
        ):
            await row.delete_clicked(MagicMock())

        parts["chronicle_service"].delete_chronicle.assert_awaited_once_with(chronicle.id)
        parts["callbacks"].on_deleted.assert_awaited_once()
        parts["callbacks"].on_changed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_confirmation_names_the_chronicle(self, make_actions, attach_page):
        row, _, chronicle = make_actions()
        attach_page(ChronicleActions)

        with patch(
            "chronicler.desktop.views.transcript.actions.confirm",
            new=AsyncMock(return_value=False),
        ) as ask:
            await row.delete_clicked(MagicMock())

        assert chronicle.title in " ".join(str(part) for part in ask.await_args[0])
