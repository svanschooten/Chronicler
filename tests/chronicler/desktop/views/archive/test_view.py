"""Tests for ArchiveView's own plumbing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.views.archive import ArchiveView
from chronicler.desktop.views.archive import view as archive_view


@pytest.fixture
def make_view():
    def _make(chronicle_service=None, task_service=None, transcript_service=None, **kwargs):
        view = ArchiveView(
            chronicle_service or AsyncMock(),
            task_service or AsyncMock(),
            AsyncMock(),
            AsyncMock(),
            transcript_service or AsyncMock(),
            **kwargs,
        )
        view.load_chronicles = AsyncMock()
        return view

    return _make


def _event(data=None):
    return MagicMock(control=MagicMock(data=data))


@pytest.mark.asyncio
async def test_mount_registers_the_file_picker_as_a_service_not_an_overlay(make_view, attach_page):
    """
    Regression test: FilePicker is a Service (flet.controls.services.service), not a visual
    control - the client fails with "Unknown control: FilePicker" if it's added to
    page.overlay, which expects renderable widgets.
    """
    view = make_view()
    page = attach_page(ArchiveView)
    page.overlay = []
    page.services = []

    await view.mount_async()

    assert view.file_picker in page.services
    assert view.file_picker not in page.overlay


@pytest.mark.asyncio
async def test_mount_attaches_every_form_and_unmount_detaches_them(make_view, attach_page):
    view = make_view()
    page = attach_page(ArchiveView)
    page.overlay = []
    page.services = []

    await view.mount_async()
    assert len(page.overlay) == 3

    view.will_unmount()
    assert page.overlay == []
    assert page.services == []


def test_show_snackbar_uses_page_show_dialog(make_view, attach_page):
    """
    Regression test: ft.Page has no `snack_bar` attribute in flet 0.86.4 - a SnackBar is
    shown via page.show_dialog(), the same mechanism as ft.AlertDialog.
    """
    view = make_view()
    page = attach_page(ArchiveView)

    view.show_snackbar("Something happened")

    (dialog,), _ = page.show_dialog.call_args
    assert isinstance(dialog, ft.SnackBar)


@pytest.mark.asyncio
async def test_load_chronicles_lists_everything_when_there_is_no_query(make_view):
    chronicle_service = AsyncMock()
    chronicle_service.list_chronicles.return_value = [Chronicle(title="A")]
    view = make_view(chronicle_service=chronicle_service)
    view.load_chronicles = ArchiveView.load_chronicles.__get__(view)
    view.update = MagicMock()

    await view.load_chronicles()

    chronicle_service.list_chronicles.assert_awaited_once()
    chronicle_service.search_chronicles.assert_not_awaited()
    assert len(view.chronicle_list.controls) == 1


@pytest.mark.asyncio
async def test_search_changed_switches_to_searching(make_view):
    chronicle_service = AsyncMock()
    chronicle_service.search_chronicles.return_value = []
    view = make_view(chronicle_service=chronicle_service)
    view.load_chronicles = ArchiveView.load_chronicles.__get__(view)
    view.update = MagicMock()

    await view.search_changed(MagicMock(data="emberfall"))

    assert view.query == "emberfall"
    chronicle_service.search_chronicles.assert_awaited_once_with("emberfall")


@pytest.mark.asyncio
async def test_load_chronicles_shows_a_placeholder_when_there_are_none(make_view):
    chronicle_service = AsyncMock()
    chronicle_service.list_chronicles.return_value = []
    view = make_view(chronicle_service=chronicle_service)
    view.load_chronicles = ArchiveView.load_chronicles.__get__(view)
    view.update = MagicMock()

    await view.load_chronicles()

    assert "No chronicles yet." in view.chronicle_list.controls[0].value


@pytest.mark.asyncio
async def test_load_chronicles_reports_a_service_failure_in_place(make_view):
    """
    A failed load must leave a visible message, not an empty list that reads as "you have no
    chronicles".
    """
    chronicle_service = AsyncMock()
    chronicle_service.list_chronicles.side_effect = RuntimeError("db is gone")
    view = make_view(chronicle_service=chronicle_service)
    view.load_chronicles = ArchiveView.load_chronicles.__get__(view)
    view.update = MagicMock()

    await view.load_chronicles()

    assert "db is gone" in view.chronicle_list.controls[0].value


@pytest.mark.asyncio
async def test_open_chronicle_clicked_forwards_the_chronicle(make_view):
    view = make_view()
    chronicle = Chronicle(title="T")

    await view.open_chronicle_clicked(_event(chronicle))

    view.on_open_chronicle.assert_awaited_once_with(chronicle)


@pytest.mark.asyncio
async def test_create_chronicle_clicked_creates_clears_and_closes(make_view, attach_page):
    chronicle_service = AsyncMock()
    view = make_view(chronicle_service=chronicle_service)
    attach_page(ArchiveView)
    view.create_form.title_field.value = "New Chronicle"

    await view.create_chronicle_clicked(MagicMock())

    chronicle_service.create_chronicle.assert_awaited_once_with("New Chronicle")
    assert view.create_form.title == ""
    assert view.create_form.dialog.open is False
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_chronicle_clicked_ignores_an_empty_title(make_view, attach_page):
    chronicle_service = AsyncMock()
    view = make_view(chronicle_service=chronicle_service)
    attach_page(ArchiveView)

    await view.create_chronicle_clicked(MagicMock())

    chronicle_service.create_chronicle.assert_not_awaited()


class TestActionsDelegateToTheSharedOperations:
    """
    Behaviour lives in ChronicleOperations and is tested there. What the archive owes is
    correct wiring: the right operation, for the chronicle whose button was clicked, and
    a reload when it says something changed.
    """

    @pytest.fixture
    def wired(self, make_view):
        view = make_view()
        view.operations = AsyncMock()
        return view

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("handler", "operation"),
        [
            ("clean_clicked", "clean"),
            ("identify_speakers_clicked", "identify_speakers"),
            ("import_audio_clicked", "import_audio"),
            ("edit_clicked", "begin_edit"),
            ("import_transcript_clicked", "begin_transcript_import"),
            ("delete_clicked", "delete"),
        ],
    )
    async def test_each_action_passes_the_clicked_chronicle(self, wired, handler, operation):
        chronicle = Chronicle(title="Session One")

        await getattr(wired, handler)(_event(chronicle))

        getattr(wired.operations, operation).assert_awaited_once_with(chronicle)

    @pytest.mark.asyncio
    async def test_linking_needs_no_chronicle(self, wired):
        await wired.link_chronicle_clicked(MagicMock())

        wired.operations.link_chronicle.assert_awaited_once_with()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("handler", "operation"),
        [
            ("identify_speakers_clicked", "identify_speakers"),
            ("import_audio_clicked", "import_audio"),
            ("delete_clicked", "delete"),
        ],
    )
    async def test_a_change_reloads_the_list(self, wired, handler, operation):
        getattr(wired.operations, operation).return_value = True

        await getattr(wired, handler)(_event(Chronicle(title="T")))

        wired.load_chronicles.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_change_leaves_the_list_alone(self, wired):
        wired.operations.delete.return_value = False

        await wired.delete_clicked(_event(Chronicle(title="T")))

        wired.load_chronicles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_header_import_menu_creates_a_chronicle_from_the_file(self, wired):
        """Its menu items carry no chronicle, which is what tells the coordinator to create one."""
        await wired.import_audio_clicked(_event(None))

        wired.operations.import_audio.assert_awaited_once_with(None)

    def test_the_view_attaches_the_operations_forms(self, make_view):
        view = make_view()

        assert set(view.operations.forms) <= set(view._forms)
        assert view.create_form in view._forms


@pytest.mark.asyncio
async def test_refresh_keeps_the_search_and_the_open_form(monkeypatch):
    """Ticket 027: a task finishing must not reset the query or touch an open form."""
    monkeypatch.setattr(archive_view, "REFRESH_SEARCH_DELAY", 0)
    chronicle_service = AsyncMock()
    chronicle_service.search_chronicles.return_value = [Chronicle(title="Budget review")]
    transcript_service = AsyncMock()
    transcript_service.search_transcripts.return_value = []
    view = ArchiveView(chronicle_service, AsyncMock(), AsyncMock(), AsyncMock(), transcript_service)
    view.update = MagicMock()
    view.query = "budget"
    form = view.create_form

    await view.refresh()

    chronicle_service.search_chronicles.assert_awaited_once_with("budget")
    chronicle_service.list_chronicles.assert_not_awaited()
    assert view.query == "budget"
    assert view.create_form is form
    assert len(view.chronicle_list.controls) == 1


def test_link_is_offered_by_default_and_hidden_for_a_thin_client(make_view):
    assert len(make_view()._link_items()) == 1
    assert make_view(can_link=False)._link_items() == []


def _searching_view(found_by_title, matches):
    chronicle_service = AsyncMock()
    chronicle_service.search_chronicles.return_value = found_by_title
    transcript_service = AsyncMock()
    transcript_service.search_transcripts.return_value = matches
    view = ArchiveView(chronicle_service, AsyncMock(), AsyncMock(), AsyncMock(), transcript_service)
    view.update = MagicMock()
    return view, transcript_service


def _texts(control) -> list[str]:
    from tests.chronicler.desktop.controls import text_values

    return text_values(control)


class TestTranscriptMatches:
    """Ticket 063: the archive search also finds what was said."""

    @pytest.mark.asyncio
    async def test_matches_follow_the_chronicles_found_by_title(self):
        from chronicler.core.models import TranscriptLine, TranscriptMatch

        said = Chronicle(title="Standup")
        line = TranscriptLine(speaker_name="Alice", text="the budget", start_time=0, end_time=1)
        view, transcripts = _searching_view(
            [Chronicle(title="Budget review")], [TranscriptMatch(chronicle=said, lines=[line])]
        )
        view.query = "budget"

        await view.load_chronicles()

        transcripts.search_transcripts.assert_awaited_once_with("budget")
        texts = _texts(view.chronicle_list)
        assert texts.index("Budget review") < texts.index("Standup")
        assert "Alice: the budget" in texts
        assert view.chronicle_list.controls[-1].data == said

    @pytest.mark.asyncio
    async def test_only_transcript_matches_replace_the_empty_message(self):
        from chronicler.core.models import TranscriptLine, TranscriptMatch

        line = TranscriptLine(text="hello", start_time=0, end_time=1)
        view, _ = _searching_view(
            [], [TranscriptMatch(chronicle=Chronicle(title="Said"), lines=[line])]
        )
        view.query = "hello"

        await view.load_chronicles()

        texts = _texts(view.chronicle_list)
        assert "Said" in texts
        assert not any("No chronicles" in text for text in texts)

    @pytest.mark.asyncio
    async def test_no_transcript_search_without_a_query(self):
        view, transcripts = _searching_view([], [])

        await view.load_chronicles()

        transcripts.search_transcripts.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_search_overtaken_by_newer_typing_is_dropped(self):
        from chronicler.core.models import TranscriptLine, TranscriptMatch

        view, transcripts = _searching_view([], [])
        stale = TranscriptMatch(
            chronicle=Chronicle(title="Stale"),
            lines=[TranscriptLine(text="old", start_time=0, end_time=1)],
        )

        async def slow_then_newer(query):
            if query == "ol":
                view.query = "old"
                await view.load_chronicles()
                return [stale]
            return []

        transcripts.search_transcripts.side_effect = slow_then_newer
        view.query = "ol"

        await view.load_chronicles()

        assert "Stale" not in _texts(view.chronicle_list)

    @pytest.mark.asyncio
    async def test_a_failed_transcript_search_says_so_and_keeps_the_list(self):
        view, transcripts = _searching_view([Chronicle(title="Kept")], [])
        transcripts.search_transcripts.side_effect = RuntimeError("disk gone")
        view.query = "x"

        await view.load_chronicles()

        texts = _texts(view.chronicle_list)
        assert "Kept" in texts
        assert any("disk gone" in text for text in texts)


def _match(chronicle, text="the budget"):
    from chronicler.core.models import TranscriptLine, TranscriptMatch

    line = TranscriptLine(speaker_name="Alice", text=text, start_time=0, end_time=1)
    return TranscriptMatch(chronicle=chronicle, lines=[line])


class TestTranscriptMatchesOnRefresh:
    """A finished task re-reads the list without the "Said in" section blinking away."""

    @pytest.mark.asyncio
    async def test_a_chronicle_found_by_title_is_not_listed_again_under_said_in(self):
        both = Chronicle(title="Budget review")
        view, _ = _searching_view([both], [_match(both), _match(Chronicle(title="Standup"))])
        view.query = "budget"

        await view.load_chronicles()

        assert _texts(view.chronicle_list).count("Budget review") == 1
        assert "Standup" in _texts(view.chronicle_list)

    @pytest.mark.asyncio
    async def test_the_section_stays_on_screen_while_a_refresh_searches_again(self, monkeypatch):
        monkeypatch.setattr(archive_view, "REFRESH_SEARCH_DELAY", 0)
        view, transcripts = _searching_view([], [_match(Chronicle(title="Standup"))])
        view.query = "budget"
        await view.load_chronicles()

        seen_while_searching = []

        async def search(query):
            seen_while_searching.extend(_texts(view.chronicle_list))
            return [_match(Chronicle(title="Standup"))]

        transcripts.search_transcripts.side_effect = search
        await view.refresh()

        assert "Standup" in seen_while_searching
        assert "Standup" in _texts(view.chronicle_list)

    @pytest.mark.asyncio
    async def test_a_new_query_does_not_show_the_old_section(self):
        view, transcripts = _searching_view([], [_match(Chronicle(title="Standup"))])
        view.query = "budget"
        await view.load_chronicles()

        seen_while_searching = []

        async def search(query):
            seen_while_searching.extend(_texts(view.chronicle_list))
            return []

        transcripts.search_transcripts.side_effect = search
        view.query = "lunch"
        await view.load_chronicles()

        assert "Standup" not in seen_while_searching
        assert "Standup" not in _texts(view.chronicle_list)

    @pytest.mark.asyncio
    async def test_tasks_finishing_together_start_one_transcript_search(self, monkeypatch):
        monkeypatch.setattr(archive_view, "REFRESH_SEARCH_DELAY", 0.05)
        view, transcripts = _searching_view([], [])
        view.query = "budget"

        await asyncio.gather(view.refresh(), view.refresh(), view.refresh())

        transcripts.search_transcripts.assert_awaited_once_with("budget")
