"""Tests for TranscriptView - layout, lifecycle and transcript rendering.

Export and the Sources panel have their own modules.
"""

from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest

from chronicler.core.models import Chronicle, Tag, TranscriptLine
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript import TranscriptView
from tests.chronicler.desktop.controls import find_controls, text_values


@pytest.fixture
def make_view():
    def _make(chronicle=None, transcript_service=None, task_service=None, **kwargs):
        view = TranscriptView(
            chronicle or Chronicle(title="Some Chronicle"),
            AsyncMock(),
            transcript_service or AsyncMock(),
            task_service or AsyncMock(),
            **kwargs,
        )
        view.file_picker = AsyncMock()
        view.transcript_area.update = MagicMock()
        return view

    return _make


# -- layout --------------------------------------------------------------------


def test_header_summarizes_the_chronicle(make_view):
    view = make_view(
        chronicle=Chronicle(title="Weekly product sync", kind="Work meeting", duration="48m")
    )

    values = text_values(view)

    assert "Weekly product sync" in values
    assert any("Work meeting" in v and "48m" in v for v in values)


def test_header_says_unknown_for_a_chronicle_with_no_duration_yet(make_view):
    view = make_view(chronicle=Chronicle(title="T", kind="Interview"))

    assert any("Unknown" in v for v in text_values(view))


def test_detail_panel_shows_status_speakers_and_tags(make_view):
    view = make_view(
        chronicle=Chronicle(
            title="T", status="Transcribed", speakers_count=4, tags=[Tag(name="product")]
        )
    )

    values = text_values(view)

    assert "Transcribed" in values
    assert "4 identified" in values
    assert "product" in values


def test_detail_panel_falls_back_when_there_are_no_tags(make_view):
    assert "No tags" in text_values(make_view())


@pytest.mark.parametrize("dark_mode", [True, False])
def test_panels_take_their_colors_from_the_palette(make_view, dark_mode):
    view = make_view(dark_mode=dark_mode)
    colors = theme_colors(dark_mode)

    panels = [c for c in find_controls(view.controls[1], lambda c: isinstance(c, ft.Container))]

    assert panels
    assert all(panel.bgcolor == colors.card for panel in panels)


# -- lifecycle -----------------------------------------------------------------


def test_did_mount_registers_the_file_picker_as_a_service_not_an_overlay(attach_page):
    """Regression test: FilePicker is a Service (flet.controls.services.service), not a
    visual control - the client fails with "Unknown control: FilePicker" if it's added
    to page.overlay. Built directly rather than through make_view, which pre-stubs
    file_picker, so did_mount exercises the real construction path.
    """
    view = TranscriptView(Chronicle(title="T"), AsyncMock(), AsyncMock(), AsyncMock())
    page = attach_page(TranscriptView)
    page.overlay = []
    page.services = []

    view.did_mount()

    assert view.file_picker is not None
    assert view.file_picker in page.services
    assert view.file_picker not in page.overlay


def test_will_unmount_removes_the_file_picker(make_view, attach_page):
    view = make_view()
    page = attach_page(TranscriptView)
    page.services = [view.file_picker]

    view.will_unmount()

    assert page.services == []


def test_show_snackbar_uses_page_show_dialog(make_view, attach_page):
    view = make_view()
    page = attach_page(TranscriptView)

    view.show_snackbar("Something happened")

    (dialog,), _ = page.show_dialog.call_args
    assert isinstance(dialog, ft.SnackBar)


@pytest.mark.asyncio
async def test_back_clicked_calls_back(make_view):
    view = make_view()

    await view.back_clicked(MagicMock())

    view.on_back.assert_awaited_once()


# -- transcript rendering -------------------------------------------------------


@pytest.mark.asyncio
async def test_load_transcript_shows_a_placeholder_when_empty(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = []
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert view.transcript_area.value == "Transcript is empty or still processing."


@pytest.mark.asyncio
async def test_load_transcript_reports_a_failure_in_the_transcript_area(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.side_effect = RuntimeError("project db missing")
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert "project db missing" in view.transcript_area.value


@pytest.mark.asyncio
async def test_load_transcript_hides_timestamps_by_default(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(speaker_name="Alice", text="Hi", start_time=65.0, end_time=66.0)
    ]
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert view.transcript_area.value == "Alice: Hi"


@pytest.mark.asyncio
async def test_lines_with_no_speaker_render_as_unknown(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(text="Hi", start_time=0.0, end_time=1.0)
    ]
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert view.transcript_area.value == "Unknown: Hi"


@pytest.mark.asyncio
async def test_show_timestamps_reformats_without_refetching(make_view):
    """Toggling the checkbox shouldn't cost a round trip or flash "Loading..." - the
    lines are already in memory."""
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(speaker_name="Alice", text="Hi", start_time=65.0, end_time=66.0)
    ]
    view = make_view(transcript_service=transcript_service)
    await view.load_transcript()
    transcript_service.get_transcript.reset_mock()

    event = MagicMock(control=MagicMock(value=True))
    await view.show_timestamps_changed(event)

    assert view.transcript_area.value == "[00:01:05] Alice: Hi"
    transcript_service.get_transcript.assert_not_awaited()

    event.control.value = False
    await view.show_timestamps_changed(event)

    assert view.transcript_area.value == "Alice: Hi"
