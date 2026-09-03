"""Tests for the Summaries panel."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.models import Chronicle, Summary
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.summaries import SummariesPanel


@pytest.fixture
def make_panel():
    def _make(summaries=None, **overrides):
        transcript_service = AsyncMock()
        transcript_service.list_summaries.return_value = summaries or []
        panel = SummariesPanel(
            Chronicle(title="Session One"),
            transcript_service,
            overrides.get("task_service") or AsyncMock(),
            theme_colors(True),
            MagicMock(),
            overrides.get("available_models"),
            overrides.get("can_summarize"),
        )
        panel.summary_list.update = MagicMock()
        return panel, transcript_service

    return _make


class TestListing:
    @pytest.mark.asyncio
    async def test_an_empty_panel_says_so(self, make_panel):
        panel, _ = make_panel()

        await panel.load()

        assert "No summaries" in panel.summary_list.controls[0].value

    @pytest.mark.asyncio
    async def test_each_summary_is_numbered_so_runs_can_be_compared(self, make_panel):
        panel, _ = make_panel(
            [
                Summary(number=1, title="First pass", content="...", model="qwen3"),
                Summary(number=2, title="Second pass", content="...", model="llama3"),
            ]
        )

        await panel.load()

        labels = [row.controls[0].controls[0].value for row in panel.summary_list.controls]
        assert labels == ["1. First pass", "2. Second pass"]

    @pytest.mark.asyncio
    async def test_the_model_that_produced_it_is_shown(self, make_panel):
        panel, _ = make_panel([Summary(number=1, content="...", model="qwen3")])

        await panel.load()

        assert panel.summary_list.controls[0].controls[0].controls[1].value == "qwen3"

    @pytest.mark.asyncio
    async def test_a_failing_listing_degrades_to_the_empty_state(self, make_panel):
        panel, transcript_service = make_panel()
        transcript_service.list_summaries.side_effect = RuntimeError("no such table")

        await panel.load()

        assert "No summaries" in panel.summary_list.controls[0].value


class TestGenerateGating:
    def test_without_a_configured_model_the_button_is_disabled_and_explains_why(self, make_panel):
        panel, _ = make_panel(can_summarize=lambda: False)

        button = panel.generate_button
        assert button.disabled is True
        assert "Configure an AI model" in button.tooltip

    def test_with_a_configured_model_the_button_is_live(self, make_panel):
        panel, _ = make_panel(can_summarize=lambda: True)

        assert panel.generate_button.disabled is False
        assert "Configure an AI model" not in panel.generate_button.tooltip

    def test_with_no_information_the_button_stays_live(self, make_panel):
        panel, _ = make_panel()

        assert panel.generate_button.disabled is False

    @pytest.mark.asyncio
    async def test_a_blocked_panel_queues_nothing_even_if_clicked(self, make_panel):
        task_service = AsyncMock()
        panel, _ = make_panel(can_summarize=lambda: False, task_service=task_service)

        await panel.generate()

        task_service.queue_summarize.assert_not_awaited()
