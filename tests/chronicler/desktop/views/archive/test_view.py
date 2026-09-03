"""Tests for ArchiveView's own plumbing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.views.archive import ArchiveView


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

    assert "No chronicles found." in view.chronicle_list.controls[0].value


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
async def test_clean_clicked_reads_the_chronicle_id_from_the_control_data(make_view):
    task_service = AsyncMock()
    view = make_view(task_service=task_service)
    view.show_snackbar = MagicMock()
    chronicle_id = uuid4()

    await view.clean_clicked(_event(chronicle_id))

    task_service.queue_clean.assert_awaited_once_with(chronicle_id)
    view.show_snackbar.assert_called_once()


@pytest.mark.asyncio
async def test_identify_speakers_clicked_refreshes_the_count_and_the_list(make_view):
    transcript_service = AsyncMock()
    transcript_service.refresh_speaker_count.return_value = 3
    view = make_view(transcript_service=transcript_service)
    view.show_snackbar = MagicMock()
    chronicle_id = uuid4()

    await view.identify_speakers_clicked(_event(chronicle_id))

    transcript_service.refresh_speaker_count.assert_awaited_once_with(chronicle_id)
    view.show_snackbar.assert_called_once_with("Found 3 speakers")
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_identify_speakers_message_is_singular_for_one_speaker(make_view):
    transcript_service = AsyncMock()
    transcript_service.refresh_speaker_count.return_value = 1
    view = make_view(transcript_service=transcript_service)
    view.show_snackbar = MagicMock()

    await view.identify_speakers_clicked(_event(uuid4()))

    view.show_snackbar.assert_called_once_with("Found 1 speaker")


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


@pytest.mark.asyncio
async def test_edit_clicked_prefills_and_opens_the_form(make_view, attach_page):
    view = make_view()
    attach_page(ArchiveView)
    chronicle = Chronicle(title="Original Title", kind="Podcast")

    await view.edit_clicked(_event(chronicle))

    assert view.editing_chronicle_id == chronicle.id
    assert view.edit_form.title_field.value == "Original Title"
    assert view.edit_form.dialog.open is True


@pytest.mark.asyncio
async def test_save_edit_clicked_persists_the_edited_chronicle(make_view, attach_page):
    existing = Chronicle(title="Old Title", kind="Unknown")
    chronicle_service = AsyncMock()
    chronicle_service.get_chronicle.return_value = existing
    view = make_view(chronicle_service=chronicle_service)
    attach_page(ArchiveView)
    view.show_snackbar = MagicMock()
    view.editing_chronicle_id = existing.id
    view.edit_form.title_field.value = "New Title"
    view.edit_form.kind_field.value = "Meeting"

    await view.save_edit_clicked(MagicMock())

    (saved,), _ = chronicle_service.update_chronicle.call_args
    assert saved.title == "New Title"
    assert saved.kind == "Meeting"
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_edit_clicked_handles_a_chronicle_deleted_meanwhile(make_view, attach_page):
    chronicle_service = AsyncMock()
    chronicle_service.get_chronicle.return_value = None
    view = make_view(chronicle_service=chronicle_service)
    attach_page(ArchiveView)
    view.show_snackbar = MagicMock()
    view.editing_chronicle_id = uuid4()

    await view.save_edit_clicked(MagicMock())

    chronicle_service.update_chronicle.assert_not_awaited()
    view.show_snackbar.assert_called_once_with("Chronicle no longer exists.")


@pytest.mark.asyncio
async def test_delete_clicked_deletes_only_after_confirmation(make_view, attach_page, monkeypatch):
    chronicle_service = AsyncMock()
    view = make_view(chronicle_service=chronicle_service)
    attach_page(ArchiveView)
    view.show_snackbar = MagicMock()
    monkeypatch.setattr(
        "chronicler.desktop.views.archive.view.confirm", AsyncMock(return_value=True)
    )
    chronicle = Chronicle(title="Doomed")

    await view.delete_clicked(_event(chronicle))

    chronicle_service.delete_chronicle.assert_awaited_once_with(chronicle.id)
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_clicked_does_nothing_when_cancelled(make_view, attach_page, monkeypatch):
    chronicle_service = AsyncMock()
    view = make_view(chronicle_service=chronicle_service)
    attach_page(ArchiveView)
    monkeypatch.setattr(
        "chronicler.desktop.views.archive.view.confirm", AsyncMock(return_value=False)
    )

    await view.delete_clicked(_event(Chronicle(title="Safe")))

    chronicle_service.delete_chronicle.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_audio_clicked_records_the_action_and_opens_the_picker(make_view):
    view = make_view()
    view.pick_file = AsyncMock()
    chronicle_id = uuid4()

    await view.import_audio_clicked(_event(chronicle_id))

    assert view.picker_action == "AUDIO"
    assert view.current_chronicle_id == chronicle_id
    view.pick_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_transcript_clicked_opens_the_options_form_first(make_view, attach_page):
    view = make_view()
    attach_page(ArchiveView)
    chronicle_id = uuid4()

    await view.import_transcript_clicked(_event(chronicle_id))

    assert view.current_chronicle_id == chronicle_id
    assert view.transcript_form.dialog.open is True
    assert view.picker_action is None


@pytest.mark.asyncio
async def test_do_transcript_import_closes_the_form_then_picks(make_view, attach_page):
    view = make_view()
    attach_page(ArchiveView)
    view.pick_file = AsyncMock()

    await view.do_transcript_import(MagicMock())

    assert view.transcript_form.dialog.open is False
    assert view.picker_action == "TRANSCRIPT"
    view.pick_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_pick_file_reports_when_there_is_no_picker(make_view):
    view = make_view()
    view.show_snackbar = MagicMock()

    await view.pick_file()

    view.show_snackbar.assert_called_once_with("File picker not available.")


@pytest.mark.asyncio
async def test_pick_file_forwards_the_first_picked_path(make_view):
    view = make_view()
    view.file_picker = AsyncMock()
    view.file_picker.pick_files.return_value = [MagicMock(path="/tmp/a.txt")]
    view.handle_file_result = AsyncMock()

    await view.pick_file(allowed_extensions=["txt"])

    view.handle_file_result.assert_awaited_once_with("/tmp/a.txt")


@pytest.mark.asyncio
async def test_pick_file_surfaces_a_picker_failure(make_view):
    view = make_view()
    view.file_picker = AsyncMock()
    view.file_picker.pick_files.side_effect = RuntimeError("no picker on this platform")
    view.show_snackbar = MagicMock()

    await view.pick_file()

    assert "no picker on this platform" in view.show_snackbar.call_args.args[0]


@pytest.mark.parametrize(
    ("action", "coordinator_method"),
    [("AUDIO", "import_audio"), ("TRANSCRIPT", "import_transcript"), ("LINK", "link_chronicle")],
)
@pytest.mark.asyncio
async def test_handle_file_result_dispatches_to_the_coordinator(
    make_view, action, coordinator_method
):
    view = make_view()
    view.show_snackbar = MagicMock()
    view.imports = MagicMock()
    setattr(view.imports, coordinator_method, AsyncMock(return_value="done"))

    view.picker_action = action
    await view.handle_file_result("/tmp/picked")

    getattr(view.imports, coordinator_method).assert_awaited_once()
    view.show_snackbar.assert_called_once_with("done")
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_file_result_shows_nothing_when_the_import_was_cancelled(make_view):
    view = make_view()
    view.show_snackbar = MagicMock()
    view.imports = MagicMock()
    view.imports.import_transcript = AsyncMock(return_value=None)

    view.picker_action = "TRANSCRIPT"
    await view.handle_file_result("/tmp/picked")

    view.show_snackbar.assert_not_called()


@pytest.mark.asyncio
async def test_handle_file_result_surfaces_errors_and_always_clears_picker_state(make_view):
    view = make_view()
    view.show_snackbar = MagicMock()
    view.imports = MagicMock()
    view.imports.import_audio = AsyncMock(side_effect=RuntimeError("disk full"))

    view.picker_action = "AUDIO"
    view.current_chronicle_id = uuid4()
    await view.handle_file_result("/tmp/picked")

    assert "disk full" in view.show_snackbar.call_args.args[0]
    assert view.picker_action is None
    assert view.current_chronicle_id is None


@pytest.mark.asyncio
async def test_ask_overwrite_or_append_offers_all_three_answers(make_view, attach_page):
    view = make_view()
    page = attach_page(ArchiveView)

    task = asyncio.ensure_future(view.ask_overwrite_or_append())
    await asyncio.sleep(0)

    (dialog,), _ = page.show_dialog.call_args
    assert [action.content for action in dialog.actions] == ["Cancel", "Append", "Overwrite"]

    await dialog.actions[2].on_click(MagicMock())
    assert await asyncio.wait_for(task, timeout=1) == "overwrite"
