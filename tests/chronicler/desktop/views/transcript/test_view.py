"""Tests for TranscriptView - layout, lifecycle and transcript rendering."""

from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft
import pytest

from chronicler.core.models import Chronicle, Tag, TranscriptLine
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript import TranscriptView
from chronicler.desktop.views.transcript.view import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    MAX_DETAIL_WIDTH,
    MIN_DETAIL_WIDTH,
    READER_MARGIN_X,
    READER_MARGIN_Y,
    READER_MIN_HEIGHT,
    READER_MIN_WIDTH,
    TRANSCRIPT_LINE_HEIGHT,
    detail_panel_width,
)
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
        view.transcript_text.update = MagicMock()
        return view

    return _make


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

    body = view.controls[-1]
    panels = [
        c
        for c in find_controls(body, lambda c: isinstance(c, ft.Container))
        if c.bgcolor is not None
    ]

    assert panels
    assert all(panel.bgcolor == colors.card for panel in panels)


def test_did_mount_registers_the_file_picker_as_a_service_not_an_overlay(attach_page):
    """
    Regression test: FilePicker is a Service (flet.controls.services.service), not a visual
    control - the client fails with "Unknown control: FilePicker" if it's added to
    page.overlay.
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


@pytest.mark.asyncio
async def test_load_transcript_shows_a_placeholder_when_empty(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = []
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert view.transcript_text.value == "Transcript is empty or still processing."


@pytest.mark.asyncio
async def test_load_transcript_reports_a_failure_in_the_transcript_body(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.side_effect = RuntimeError("project db missing")
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert "project db missing" in view.transcript_text.value


@pytest.mark.asyncio
async def test_load_transcript_hides_timestamps_by_default(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(speaker_name="Alice", text="Hi", start_time=65.0, end_time=66.0)
    ]
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert view.transcript_text.value == "Alice: Hi"


@pytest.mark.asyncio
async def test_lines_with_no_speaker_render_as_unknown(make_view):
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(text="Hi", start_time=0.0, end_time=1.0)
    ]
    view = make_view(transcript_service=transcript_service)

    await view.load_transcript()

    assert view.transcript_text.value == "Unknown: Hi"


@pytest.mark.asyncio
async def test_show_timestamps_reformats_without_refetching(make_view):
    """
    Toggling the checkbox shouldn't cost a round trip or flash "Loading..." - the lines are
    already in memory.
    """
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(speaker_name="Alice", text="Hi", start_time=65.0, end_time=66.0)
    ]
    view = make_view(transcript_service=transcript_service)
    await view.load_transcript()
    transcript_service.get_transcript.reset_mock()

    event = MagicMock(control=MagicMock(value=True))
    await view.show_timestamps_changed(event)

    assert view.transcript_text.value == "[00:01:05] Alice: Hi"
    transcript_service.get_transcript.assert_not_awaited()

    event.control.value = False
    await view.show_timestamps_changed(event)

    assert view.transcript_text.value == "Alice: Hi"


class TestReadableLayout:
    """
    The read view used to be a read-only TextField capped at sixteen lines with a blank
    line between turns: it stopped partway down the panel however tall the window was,
    and hid everything past the cap.
    """

    def test_it_fills_the_panel_and_scrolls(self, make_view):
        view = make_view()

        assert view.transcript_area.expand is True
        assert view.transcript_area.scroll == ft.ScrollMode.AUTO

    def test_turns_are_one_line_apart_not_two(self, make_view):
        view = make_view()
        view.transcript_lines = [
            TranscriptLine(speaker_name="Alice", text="Hi", start_time=0.0, end_time=1.0),
            TranscriptLine(speaker_name="Bob", text="Hello", start_time=1.0, end_time=2.0),
        ]

        assert view._transcript_body() == "Alice: Hi\nBob: Hello"

    def test_the_spacing_is_a_line_height_rather_than_a_blank_line(self, make_view):
        view = make_view()

        assert view.transcript_text.style.height == TRANSCRIPT_LINE_HEIGHT

    def test_the_whole_transcript_stays_selectable_as_one_block(self, make_view):
        """Read and edit are separate modes precisely so this holds."""
        view = make_view()

        assert view.transcript_text.selectable is True

    def test_nothing_is_cut_off_by_a_line_cap(self, make_view):
        view = make_view()
        view.transcript_lines = [
            TranscriptLine(speaker_name="Alice", text=f"Line {n}", start_time=n, end_time=n + 1)
            for n in range(200)
        ]

        assert len(view._transcript_body().splitlines()) == 200

    @pytest.mark.asyncio
    async def test_the_timestamp_toggle_still_reformats_both_ways(self, make_view):
        transcript_service = AsyncMock()
        transcript_service.get_transcript.return_value = [
            TranscriptLine(speaker_name="Alice", text="Hi", start_time=65.0, end_time=66.0),
            TranscriptLine(speaker_name="Bob", text="Hello", start_time=70.0, end_time=71.0),
        ]
        view = make_view(transcript_service=transcript_service)
        await view.load_transcript()

        await view.show_timestamps_changed(MagicMock(control=MagicMock(value=True)))
        assert view.transcript_text.value == "[00:01:05] Alice: Hi\n[00:01:10] Bob: Hello"

        await view.show_timestamps_changed(MagicMock(control=MagicMock(value=False)))
        assert view.transcript_text.value == "Alice: Hi\nBob: Hello"


class TestRecordButton:
    """
    Recording runs on this machine in every deployment mode, so the button asks the local
    extras rather than the service layer. See docs/optional-extras.md.
    """

    def test_it_is_offered_when_the_extra_is_installed(self, make_view):
        with patch("chronicler.core.extras.is_usable", return_value=True):
            button = make_view()._record_button()

        assert button.disabled is False

    def test_a_build_that_cannot_record_says_so_instead_of_erroring(self, make_view):
        """A packaged build without it cannot be fixed from a dialog, so it does not open one."""
        with patch("chronicler.core.extras.is_usable", return_value=False):
            button = make_view()._record_button()

        assert button.disabled is True
        assert "not available" in button.tooltip


class TestFocusedReader:
    """
    The reading dialog was a fixed 760x520 island, which is the opposite of what a
    focused reading mode is for on a large monitor.
    """

    def test_it_is_sized_from_the_window(self, make_view, attach_page):
        page = attach_page(TranscriptView)
        page.width, page.height = 2400, 1400
        view = make_view()
        reader = ft.Container()

        view._size_reader(reader)

        assert reader.width == 2400 - READER_MARGIN_X
        assert reader.height == 1400 - READER_MARGIN_Y

    def test_a_small_window_still_leaves_something_readable(self, make_view, attach_page):
        page = attach_page(TranscriptView)
        page.width, page.height = 400, 300
        view = make_view()
        reader = ft.Container()

        view._size_reader(reader)

        assert reader.width == READER_MIN_WIDTH
        assert reader.height == READER_MIN_HEIGHT

    def test_a_window_that_has_not_reported_its_size_falls_back(self, make_view, attach_page):
        page = attach_page(TranscriptView)
        page.width, page.height = None, None
        view = make_view()
        reader = ft.Container()

        view._size_reader(reader)

        assert reader.width == DEFAULT_PAGE_WIDTH - READER_MARGIN_X
        assert reader.height == DEFAULT_PAGE_HEIGHT - READER_MARGIN_Y

    def test_fullscreen_is_offered_in_the_desktop_window(self, make_view, attach_page):
        page = attach_page(TranscriptView)
        page.web = False
        view = make_view()

        assert view._can_go_fullscreen() is True

    def test_fullscreen_is_hidden_in_a_browser_tab(self, make_view, attach_page):
        """`page.window` is inert there, so the button would do nothing visible."""
        page = attach_page(TranscriptView)
        page.web = True
        view = make_view()

        assert view._can_go_fullscreen() is False


class TestDetailPanelWidth:
    def test_a_wide_window_gets_a_share_of_it(self):
        width = detail_panel_width(2400)

        assert MIN_DETAIL_WIDTH < width <= MAX_DETAIL_WIDTH

    def test_a_narrow_window_keeps_the_readable_floor(self):
        assert detail_panel_width(600) == MIN_DETAIL_WIDTH

    def test_an_ultrawide_window_stops_at_the_ceiling(self):
        assert detail_panel_width(7680) == MAX_DETAIL_WIDTH

    def test_it_grows_with_the_window_in_between(self):
        assert detail_panel_width(1200) < detail_panel_width(1800)

    def test_an_unknown_width_falls_back_to_the_floor(self):
        assert detail_panel_width(None) == MIN_DETAIL_WIDTH

    def test_it_never_takes_more_than_a_third_of_the_window(self):
        for page_width in (1000, 1440, 1920, 2560):
            assert detail_panel_width(page_width) <= page_width / 3 or (
                detail_panel_width(page_width) == MIN_DETAIL_WIDTH
            )


class TestResizing:
    def test_a_resize_widens_the_detail_panel(self, make_view, attach_page):
        view = make_view()
        page = attach_page(TranscriptView)
        page.width = 2400

        view.page_resized(MagicMock())

        assert view.detail_panel.width == detail_panel_width(2400)

    def test_a_resize_before_the_panel_is_painted_is_harmless(self, make_view, attach_page):
        view = make_view()
        page = attach_page(TranscriptView)
        page.width = None

        view.page_resized(MagicMock())

        assert view.detail_panel.width == MIN_DETAIL_WIDTH


class TestChronicleActions:
    def test_the_action_row_is_shown(self, make_view):
        view = make_view()

        assert view.actions is not None
        assert view.actions.chronicle is view.chronicle

    def test_summaries_are_gated_on_the_server_capability(self, make_view):
        allowed = make_view(capabilities=lambda: {"summarize"})
        blocked = make_view(capabilities=lambda: set())

        assert allowed.actions.can_summarize() is True
        assert blocked.actions.can_summarize() is False

    def test_with_no_capability_information_the_action_stays_available(self, make_view):
        view = make_view()

        assert view.actions.can_summarize() is True


class TestEditMode:
    def test_it_opens_in_read_mode(self, make_view):
        view = make_view()

        assert view.editing is False
        assert view.transcript_body.content is view.transcript_area

    @pytest.mark.asyncio
    async def test_toggling_swaps_in_the_editor(self, make_view, attach_page):
        view = make_view()
        attach_page(TranscriptView)
        view.editor.load = AsyncMock()

        await view.edit_toggled(MagicMock())

        assert view.editing is True
        assert view.transcript_body.content is view.editor
        view.editor.load.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_toggling_back_returns_to_the_read_view(self, make_view, attach_page):
        view = make_view()
        attach_page(TranscriptView)
        view.editor.load = AsyncMock()
        view.load_transcript = AsyncMock()

        await view.edit_toggled(MagicMock())
        await view.edit_toggled(MagicMock())

        assert view.editing is False
        assert view.transcript_body.content is view.transcript_area
        view.load_transcript.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_timestamp_checkbox_is_disabled_while_editing(self, make_view, attach_page):
        """Edit rows always show their own timestamp, so the read-view toggle means nothing."""
        view = make_view()
        attach_page(TranscriptView)
        view.editor.load = AsyncMock()

        await view.edit_toggled(MagicMock())

        assert view.timestamps_checkbox.disabled is True

    @pytest.mark.asyncio
    async def test_the_button_says_what_it_will_do_next(self, make_view, attach_page):
        view = make_view()
        attach_page(TranscriptView)
        view.editor.load = AsyncMock()

        assert view.edit_toggle.tooltip == "Edit the transcript"
        await view.edit_toggled(MagicMock())
        assert view.edit_toggle.tooltip == "Finish editing"

    @pytest.mark.asyncio
    async def test_a_reload_while_editing_does_not_rebuild_the_view(self, make_view, attach_page):
        """Rebuilding would drop the user back into read mode mid-edit."""
        rebuild = AsyncMock()
        view = make_view(on_reload=rebuild)
        attach_page(TranscriptView)
        view.editor.load = AsyncMock()
        view.load_transcript = AsyncMock()

        await view.edit_toggled(MagicMock())
        await view.reload()

        rebuild.assert_not_awaited()
