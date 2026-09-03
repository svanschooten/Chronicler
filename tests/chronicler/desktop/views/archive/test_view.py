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
async def test_import_audio_imports_into_the_chosen_chronicle(make_view):
    view = make_view()
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = "/audio/a.mp3"
    view.imports = MagicMock(import_audio=AsyncMock(return_value="Added a.mp3"))
    view.show_snackbar = MagicMock()
    chronicle_id = uuid4()

    await view.import_audio_clicked(_event(chronicle_id))

    view.imports.import_audio.assert_awaited_once_with(chronicle_id, "/audio/a.mp3")
    view.show_snackbar.assert_called_once_with("Added a.mp3")
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_audio_only_offers_audio_extensions(make_view):
    view = make_view()
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = None

    await view.import_audio_clicked(_event(uuid4()))

    assert "mp3" in view.picker.pick_file.await_args[0][0]


@pytest.mark.asyncio
async def test_cancelling_the_audio_picker_imports_nothing(make_view):
    view = make_view()
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = None
    view.imports = MagicMock(import_audio=AsyncMock())

    await view.import_audio_clicked(_event(uuid4()))

    view.imports.import_audio.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_transcript_clicked_opens_the_options_form_first(make_view, attach_page):
    view = make_view()
    attach_page(ArchiveView)
    chronicle_id = uuid4()

    await view.import_transcript_clicked(_event(chronicle_id))

    assert view.pending_chronicle_id == chronicle_id
    assert view.transcript_form.dialog.open is True


@pytest.mark.asyncio
async def test_do_transcript_import_closes_the_form_then_picks_and_imports(make_view, attach_page):
    view = make_view()
    attach_page(ArchiveView)
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = "/t/session.txt"
    view.imports = MagicMock(import_transcript=AsyncMock(return_value="Queued"))
    view.pending_chronicle_id = uuid4()

    await view.do_transcript_import(MagicMock())

    assert view.transcript_form.dialog.open is False
    assert view.imports.import_transcript.await_args[0][1] == "/t/session.txt"
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_linking_a_project_database_only_offers_db_files(make_view):
    view = make_view()
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = None

    await view.link_chronicle_clicked(MagicMock())

    assert view.picker.pick_file.await_args[0][0] == ["db"]


@pytest.mark.asyncio
async def test_linking_a_project_database_registers_it(make_view):
    view = make_view()
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = "/elsewhere/campaign/project.db"
    view.imports = MagicMock(link_chronicle=AsyncMock(return_value="Linked 'campaign'"))
    view.show_snackbar = MagicMock()

    await view.link_chronicle_clicked(MagicMock())

    view.imports.link_chronicle.assert_awaited_once_with("/elsewhere/campaign/project.db")
    view.show_snackbar.assert_called_once_with("Linked 'campaign'")


@pytest.mark.asyncio
async def test_a_failing_import_is_reported_and_the_list_still_reloads(make_view):
    view = make_view()
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = "/audio/a.mp3"
    view.imports = MagicMock(import_audio=AsyncMock(side_effect=RuntimeError("disk full")))
    view.show_snackbar = MagicMock()

    await view.import_audio_clicked(_event(uuid4()))

    assert "disk full" in view.show_snackbar.call_args.args[0]
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_cancelled_transcript_import_says_nothing(make_view, attach_page):
    view = make_view()
    attach_page(ArchiveView)
    view.picker = AsyncMock()
    view.picker.pick_file.return_value = "/t/session.txt"
    view.imports = MagicMock(import_transcript=AsyncMock(return_value=None))
    view.show_snackbar = MagicMock()

    await view.do_transcript_import(MagicMock())

    view.show_snackbar.assert_not_called()


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
