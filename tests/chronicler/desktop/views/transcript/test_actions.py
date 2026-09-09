"""Tests for the chronicle action row inside the transcript view.

The operations themselves are tested in tests/chronicler/desktop/test_operations.py; what
the row owes is layout and correct wiring.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.actions import ChronicleActionCallbacks, ChronicleActions
from tests.chronicler.desktop.controls import find_controls


@pytest.fixture
def make_actions():
    def _make(can_summarize=None):
        chronicle = Chronicle(id=uuid4(), title="Session One")
        operations = AsyncMock()
        callbacks = ChronicleActionCallbacks(
            on_changed=AsyncMock(), on_deleted=AsyncMock(), on_summarize=AsyncMock()
        )
        row = ChronicleActions(chronicle, operations, theme_colors(True), callbacks, can_summarize)
        return row, operations, callbacks, chronicle

    return _make


def _tooltips(row) -> str:
    return " ".join(
        control.tooltip or ""
        for control in find_controls(row, lambda c: bool(getattr(c, "tooltip", None)))
    )


class TestTheRow:
    def test_it_offers_every_chronicle_level_action(self, make_actions):
        row, _, _, _ = make_actions()

        shown = _tooltips(row).lower()
        for expected in ("import audio", "import transcript", "clean", "speakers", "summary"):
            assert expected in shown

    def test_edit_and_delete_are_reachable_here_too(self, make_actions):
        row, _, _, _ = make_actions()

        tooltips = _tooltips(row)
        assert "Edit" in tooltips
        assert "Delete" in tooltips

    def test_the_summary_action_is_disabled_and_explains_itself(self, make_actions):
        row, _, _, _ = make_actions(can_summarize=lambda: False)

        disabled = [
            c for c in find_controls(row, lambda c: isinstance(c, ft.IconButton)) if c.disabled
        ]
        assert len(disabled) == 1
        assert "Configure an AI model" in disabled[0].tooltip

    def test_nothing_is_disabled_when_summarising_is_available(self, make_actions):
        row, _, _, _ = make_actions(can_summarize=lambda: True)

        assert not [
            c for c in find_controls(row, lambda c: isinstance(c, ft.IconButton)) if c.disabled
        ]


class TestWiring:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("handler", "operation"),
        [
            ("clean_clicked", "clean"),
            ("identify_speakers_clicked", "identify_speakers"),
            ("import_audio_clicked", "import_audio"),
            ("import_transcript_clicked", "begin_transcript_import"),
            ("edit_clicked", "begin_edit"),
            ("delete_clicked", "delete"),
        ],
    )
    async def test_each_button_calls_its_operation_for_this_chronicle(
        self, make_actions, handler, operation
    ):
        row, operations, _, chronicle = make_actions()

        await getattr(row, handler)(MagicMock())

        getattr(operations, operation).assert_awaited_once_with(chronicle)

    @pytest.mark.asyncio
    async def test_a_change_reloads_the_view(self, make_actions):
        row, operations, callbacks, _ = make_actions()
        operations.clean.return_value = True

        await row.clean_clicked(MagicMock())

        callbacks.on_changed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_change_leaves_the_view_alone(self, make_actions):
        row, operations, callbacks, _ = make_actions()
        operations.import_audio.return_value = False

        await row.import_audio_clicked(MagicMock())

        callbacks.on_changed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleting_leaves_the_view_rather_than_reloading_it(self, make_actions):
        """Reloading a view for a chronicle that no longer exists fails immediately."""
        row, operations, callbacks, _ = make_actions()
        operations.delete.return_value = True

        await row.delete_clicked(MagicMock())

        callbacks.on_deleted.assert_awaited_once()
        callbacks.on_changed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_cancelled_delete_goes_nowhere(self, make_actions):
        row, operations, callbacks, _ = make_actions()
        operations.delete.return_value = False

        await row.delete_clicked(MagicMock())

        callbacks.on_deleted.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_summarising_hands_off_to_the_summaries_panel(self, make_actions):
        row, _, callbacks, _ = make_actions()

        await row.summarize_clicked(MagicMock())

        callbacks.on_summarize.assert_awaited_once()

    def test_the_forms_come_from_the_shared_operations(self, make_actions):
        row, operations, _, _ = make_actions()

        assert row.forms is operations.forms
