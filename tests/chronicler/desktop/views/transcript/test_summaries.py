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
            overrides.get("model_error"),
            overrides.get("default_model"),
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


class TestExplainingAnEmptyModelList:
    @pytest.mark.asyncio
    async def test_the_discovery_error_is_shown_when_there_are_no_models(
        self, make_panel, attach_page
    ):
        """An unreachable gateway used to look identical to one with no models."""
        import asyncio

        panel, _ = make_panel(
            available_models=lambda: [], model_error=lambda: "Could not reach http://localhost:8080"
        )
        page = attach_page(SummariesPanel)

        task = asyncio.ensure_future(panel._ask_options([]))
        await asyncio.sleep(0)

        (dialog,), _ = page.show_dialog.call_args
        assert "Could not reach" in dialog.content.controls[1].error_text

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_no_error_is_shown_when_models_were_found(self, make_panel, attach_page):
        import asyncio

        panel, _ = make_panel(model_error=lambda: "stale error")
        page = attach_page(SummariesPanel)

        task = asyncio.ensure_future(panel._ask_options(["qwen3"]))
        await asyncio.sleep(0)

        (dialog,), _ = page.show_dialog.call_args
        assert dialog.content.controls[1].error_text is None

        await dialog.actions[0].on_click(MagicMock())
        await asyncio.wait_for(task, timeout=1)


class TestModelChoice:
    def test_the_configured_default_starts_selected(self, make_panel):
        """Configuring a model and then being handed someone else's was the surprise."""
        panel, _ = make_panel(default_model=lambda: "qwen3")

        offered, selected = panel._model_options(["llama", "qwen3", "mistral"])

        assert selected == "qwen3"
        assert offered == ["llama", "qwen3", "mistral"]

    def test_a_default_the_gateway_did_not_list_is_still_offered(self, make_panel):
        panel, _ = make_panel(default_model=lambda: "venice/uncensored")

        offered, selected = panel._model_options(["llama"])

        assert selected == "venice/uncensored"
        assert offered == ["venice/uncensored", "llama"]

    def test_without_a_default_the_first_model_is_selected(self, make_panel):
        panel, _ = make_panel(default_model=lambda: None)

        offered, selected = panel._model_options(["llama", "qwen3"])

        assert selected == "llama"
        assert offered == ["llama", "qwen3"]

    def test_no_models_and_no_default_selects_nothing(self, make_panel):
        panel, _ = make_panel()

        offered, selected = panel._model_options([])

        assert (offered, selected) == ([], None)
