import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import flet as ft
import pytest

from chronicler.core.file_staging import stage_local_file
from chronicler.core.models import Chronicle
from chronicler.desktop.views.archive import ArchiveView


def _make_view(tmp_path, chronicle_service=None, task_service=None, transcript_service=None):
    imports_dir = tmp_path / "workspace" / "imports"
    imports_dir.mkdir(parents=True)

    async def stage_file(local_path: str) -> str:
        return str(stage_local_file(Path(local_path), imports_dir))

    view = ArchiveView(
        chronicle_service or AsyncMock(),
        task_service or AsyncMock(),
        AsyncMock(),
        stage_file,
        transcript_service or AsyncMock(),
    )
    # ArchiveView isn't attached to a live Flet Page in this unit test (Control.page
    # walks the parent chain and raises if not found) - these two only touch page/UI
    # refresh, not the staging behavior under test, so stub them out.
    view.show_snackbar = MagicMock()
    view.load_chronicles = AsyncMock()
    return view, imports_dir


def _attach_mock_page(view):
    """Same problem as show_snackbar above: `page` is a read-only property (walks the
    parent chain, raises if unattached), so it can't be assigned directly - patch the
    class attribute instead. Returns the patcher so the caller controls its lifetime.
    """
    mock_page = MagicMock(spec=ft.Page)
    patcher = patch.object(ArchiveView, "page", new_callable=PropertyMock)
    page_prop = patcher.start()
    page_prop.return_value = mock_page
    return patcher, mock_page


@pytest.mark.asyncio
async def test_handle_file_result_stages_audio_source_outside_workspace(tmp_path):
    """Importing an audio source no longer queues a transcription - it just stages
    the file (see ChronicleService.add_audio_source); transcribing a specific source
    with a speaker assigned is a separate action from the transcript view's Sources
    panel."""
    picked_file = tmp_path / "Downloads" / "recording.mp3"
    picked_file.parent.mkdir(parents=True)
    picked_file.write_text("fake audio")

    chronicle_service = AsyncMock()
    view, imports_dir = _make_view(tmp_path, chronicle_service=chronicle_service)
    view.picker_action = "AUDIO"
    chronicle_id = uuid4()
    view.current_chronicle_id = chronicle_id
    view.chronicle_list = MagicMock()

    await view.handle_file_result(str(picked_file))

    # handle_file_result resets current_chronicle_id to None in its finally block, so
    # compare against the value captured before the call.
    chronicle_service.add_audio_source.assert_awaited_once()
    called_chronicle_id, queued_path, original_name = (
        chronicle_service.add_audio_source.call_args.args
    )
    assert called_chronicle_id == chronicle_id
    assert Path(queued_path).resolve().is_relative_to(imports_dir.resolve())
    assert Path(queued_path).name != "recording.mp3"
    assert original_name == "recording.mp3"


@pytest.mark.asyncio
async def test_handle_file_result_audio_creates_chronicle_without_source_file(tmp_path):
    """create_chronicle no longer gets a source_file= for an audio import - the file
    lives in the durable sources/ dir now (see add_audio_source), and a single
    source_file field can't represent a chronicle with multiple tracks anyway."""
    picked_file = tmp_path / "Downloads" / "recording.mp3"
    picked_file.parent.mkdir(parents=True)
    picked_file.write_text("fake audio")

    chronicle_service = AsyncMock()
    chronicle_service.create_chronicle.return_value = Chronicle(title="recording")
    view, _ = _make_view(tmp_path, chronicle_service=chronicle_service)
    view.picker_action = "AUDIO"
    view.current_chronicle_id = None
    view.chronicle_list = MagicMock()

    await view.handle_file_result(str(picked_file))

    chronicle_service.create_chronicle.assert_awaited_once_with("recording")
    chronicle_service.add_audio_source.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_file_result_stages_transcript_import_and_creates_chronicle(tmp_path):
    picked_file = tmp_path / "Downloads" / "transcript.txt"
    picked_file.parent.mkdir(parents=True)
    picked_file.write_text("Alice: hi\n")

    chronicle_service = AsyncMock()
    chronicle_service.create_chronicle.return_value = Chronicle(title="transcript")
    task_service = AsyncMock()

    view, imports_dir = _make_view(
        tmp_path, chronicle_service=chronicle_service, task_service=task_service
    )
    view.picker_action = "TRANSCRIPT"
    view.current_chronicle_id = None
    view.chronicle_list = MagicMock()
    view.transcript_regex = MagicMock(value=None)
    view.transcript_speaker_group = MagicMock(value="1")
    view.transcript_text_group = MagicMock(value="2")

    await view.handle_file_result(str(picked_file))

    chronicle_service.create_chronicle.assert_awaited_once()
    task_service.queue_import.assert_awaited_once()
    _chronicle_id, queued_path = task_service.queue_import.call_args.args
    assert Path(queued_path).resolve().is_relative_to(imports_dir.resolve())
    assert task_service.queue_import.call_args.kwargs["timestamp_group"] is None


@pytest.mark.asyncio
async def test_handle_file_result_transcript_import_with_timestamp_group(tmp_path):
    picked_file = tmp_path / "Downloads" / "transcript.txt"
    picked_file.parent.mkdir(parents=True)
    picked_file.write_text("[00:00:05] Alice: hi\n")

    chronicle_service = AsyncMock()
    chronicle_service.create_chronicle.return_value = Chronicle(title="transcript")
    task_service = AsyncMock()

    view, _ = _make_view(
        tmp_path, chronicle_service=chronicle_service, task_service=task_service
    )
    view.picker_action = "TRANSCRIPT"
    view.current_chronicle_id = None
    view.chronicle_list = MagicMock()
    view.transcript_regex = MagicMock(value=r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$")
    view.transcript_speaker_group = MagicMock(value="2")
    view.transcript_text_group = MagicMock(value="3")
    view.transcript_timestamp_group = MagicMock(value="1")

    await view.handle_file_result(str(picked_file))

    assert task_service.queue_import.call_args.kwargs["timestamp_group"] == 1


def _transcript_import_view(tmp_path, existing_lines, task_service=None):
    picked_file = tmp_path / "Downloads" / "transcript.txt"
    picked_file.parent.mkdir(parents=True)
    picked_file.write_text("Alice: hi\n")

    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = existing_lines
    view, imports_dir = _make_view(
        tmp_path, task_service=task_service, transcript_service=transcript_service
    )
    view.picker_action = "TRANSCRIPT"
    view.current_chronicle_id = uuid4()
    view.chronicle_list = MagicMock()
    view.transcript_regex = MagicMock(value=None)
    view.transcript_speaker_group = MagicMock(value="1")
    view.transcript_text_group = MagicMock(value="2")
    return view, picked_file, transcript_service


@pytest.mark.asyncio
async def test_transcript_import_into_empty_chronicle_skips_confirmation(tmp_path):
    task_service = AsyncMock()
    view, picked_file, transcript_service = _transcript_import_view(
        tmp_path, existing_lines=[], task_service=task_service
    )
    view._ask_overwrite_or_append = AsyncMock()

    await view.handle_file_result(str(picked_file))

    view._ask_overwrite_or_append.assert_not_awaited()
    task_service.queue_import.assert_awaited_once()
    assert task_service.queue_import.call_args.kwargs["append"] is False


@pytest.mark.asyncio
async def test_transcript_import_into_existing_transcript_asks_and_cancels(tmp_path):
    task_service = AsyncMock()
    view, picked_file, transcript_service = _transcript_import_view(
        tmp_path, existing_lines=[MagicMock()], task_service=task_service
    )
    view._ask_overwrite_or_append = AsyncMock(return_value="cancel")

    await view.handle_file_result(str(picked_file))

    view._ask_overwrite_or_append.assert_awaited_once()
    task_service.queue_import.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcript_import_into_existing_transcript_can_append(tmp_path):
    task_service = AsyncMock()
    view, picked_file, transcript_service = _transcript_import_view(
        tmp_path, existing_lines=[MagicMock()], task_service=task_service
    )
    view._ask_overwrite_or_append = AsyncMock(return_value="append")

    await view.handle_file_result(str(picked_file))

    task_service.queue_import.assert_awaited_once()
    assert task_service.queue_import.call_args.kwargs["append"] is True


@pytest.mark.asyncio
async def test_transcript_import_into_existing_transcript_can_overwrite(tmp_path):
    task_service = AsyncMock()
    view, picked_file, transcript_service = _transcript_import_view(
        tmp_path, existing_lines=[MagicMock()], task_service=task_service
    )
    view._ask_overwrite_or_append = AsyncMock(return_value="overwrite")

    await view.handle_file_result(str(picked_file))

    task_service.queue_import.assert_awaited_once()
    assert task_service.queue_import.call_args.kwargs["append"] is False


@pytest.mark.asyncio
async def test_ask_overwrite_or_append_resolves_from_button_click(tmp_path):
    """Exercises the actual show_dialog()/pop_dialog() mechanism (not just
    handle_file_result's use of it): clicking "Append" must resolve the awaited call
    to "append" and close the dialog via pop_dialog() - not by removing it from
    page.overlay immediately, which drops AlertDialog's close animation/dismiss
    callback and leaves it stuck open on screen (the actual bug this regression test
    guards against - the future resolved and the import proceeded, so "the buttons
    worked", but the dialog never visually closed).
    """
    view, _ = _make_view(tmp_path)
    patcher, mock_page = _attach_mock_page(view)

    try:
        task = asyncio.ensure_future(view._ask_overwrite_or_append())
        await asyncio.sleep(0)  # let it reach the dialog-shown await point

        mock_page.show_dialog.assert_called_once()
        (dialog,), _ = mock_page.show_dialog.call_args
        append_button = dialog.actions[1]
        assert append_button.content == "Append"
        await append_button.on_click(MagicMock())

        result = await asyncio.wait_for(task, timeout=1)
    finally:
        patcher.stop()

    assert result == "append"
    mock_page.pop_dialog.assert_called_once()


@pytest.mark.asyncio
async def test_mount_async_registers_file_picker_as_service_not_overlay(tmp_path):
    """Regression test: FilePicker is a Service (flet.controls.services.service),
    not a visual control - the client fails with "Unknown control: FilePicker" if
    it's added to page.overlay (which expects renderable widgets). It must be
    registered through page.services instead.
    """
    view, _ = _make_view(tmp_path)
    patcher, mock_page = _attach_mock_page(view)
    mock_page.overlay = []
    mock_page.services = []

    try:
        await view.mount_async()
    finally:
        patcher.stop()

    assert view.file_picker in mock_page.services
    assert view.file_picker not in mock_page.overlay


@pytest.mark.asyncio
async def test_handle_file_result_link_action_does_not_stage(tmp_path):
    """LINK references an external project.db directly - it must not be copied into
    the workspace (that would defeat the point of linking an external chronicle)."""
    external_db = tmp_path / "external" / "project.db"
    external_db.parent.mkdir(parents=True)
    external_db.write_text("not a real db")

    chronicle_service = AsyncMock()
    view, imports_dir = _make_view(tmp_path, chronicle_service=chronicle_service)
    view.picker_action = "LINK"
    view.chronicle_list = MagicMock()

    await view.handle_file_result(str(external_db))

    chronicle_service.create_chronicle.assert_awaited_once()
    kwargs = chronicle_service.create_chronicle.call_args.kwargs
    assert kwargs["project_path"] == str(external_db)
    assert list(imports_dir.iterdir()) == []


def _find_controls(control, predicate):
    """Depth-first walk of a Flet control tree, collecting nodes matching predicate."""
    found = []
    if predicate(control):
        found.append(control)
    for attr in ("controls", "items"):
        for child in getattr(control, attr, None) or []:
            found.extend(_find_controls(child, predicate))
    content = getattr(control, "content", None)
    if content is not None:
        found.extend(_find_controls(content, predicate))
    return found


def test_card_action_controls_bind_async_handlers_directly(tmp_path):
    """Regression test: a per-card on_click that is a `lambda e: self.async_method(e)`
    is never awaited by Flet (it only checks inspect.iscoroutinefunction on the handler
    object itself, not on what it returns) - the coroutine is silently dropped. Every
    per-card action must bind the bound async method directly and carry the chronicle
    id via `data`, not via a lambda closure.
    """
    view, _ = _make_view(tmp_path)
    chronicle = Chronicle(title="Some Chronicle")

    card = view.create_chronicle_card(chronicle)

    action_controls = _find_controls(
        card, lambda c: isinstance(c, (ft.PopupMenuItem, ft.IconButton)) and c is not None
    )
    # "Transcribe Audio"/"Import Transcript" PopupMenuItems, "Edit", "Clean",
    # "Identify Speakers" and "Delete" IconButtons.
    per_card_action_controls = [c for c in action_controls if getattr(c, "on_click", None)]
    assert len(per_card_action_controls) == 6

    # Edit and Delete need the full Chronicle (to pre-fill the edit dialog / name the
    # chronicle in the delete confirmation); every other action only needs the id.
    needs_full_chronicle = {view.edit_clicked, view.delete_clicked}
    for control in per_card_action_controls:
        assert inspect.iscoroutinefunction(control.on_click), (
            f"{control} on_click must be an async function bound directly, not a lambda"
        )
        expected_data = chronicle if control.on_click in needs_full_chronicle else chronicle.id
        assert control.data == expected_data


@pytest.mark.asyncio
async def test_clean_clicked_reads_chronicle_id_from_event_control_data(tmp_path):
    task_service = AsyncMock()
    view, _ = _make_view(tmp_path, task_service=task_service)
    chronicle_id = uuid4()
    fake_event = MagicMock(control=MagicMock(data=chronicle_id))

    await view.clean_clicked(fake_event)

    task_service.queue_clean.assert_awaited_once_with(chronicle_id)
    view.show_snackbar.assert_called_once()


@pytest.mark.asyncio
async def test_identify_speakers_clicked_reads_chronicle_id_and_refreshes(tmp_path):
    transcript_service = AsyncMock()
    transcript_service.refresh_speaker_count.return_value = 3
    view, _ = _make_view(tmp_path, transcript_service=transcript_service)
    chronicle_id = uuid4()
    fake_event = MagicMock(control=MagicMock(data=chronicle_id))

    await view.identify_speakers_clicked(fake_event)

    transcript_service.refresh_speaker_count.assert_awaited_once_with(chronicle_id)
    view.show_snackbar.assert_called_once()
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_clicked_prefills_dialog_from_chronicle(tmp_path):
    view, _ = _make_view(tmp_path)
    patcher, _ = _attach_mock_page(view)
    chronicle = Chronicle(
        title="Original Title", description="Original desc", kind="Podcast", duration="1h"
    )
    fake_event = MagicMock(control=MagicMock(data=chronicle))

    try:
        await view.edit_clicked(fake_event)
    finally:
        patcher.stop()

    assert view.editing_chronicle_id == chronicle.id
    assert view.edit_title.value == "Original Title"
    assert view.edit_description.value == "Original desc"
    assert view.edit_kind.value == "Podcast"
    assert view.edit_duration.value == "1h"
    assert view.edit_dialog.open is True


@pytest.mark.asyncio
async def test_edit_clicked_blanks_kind_field_when_unknown(tmp_path):
    """"Unknown" is the model default, not a real value the user typed - the edit
    field should start blank rather than round-tripping the placeholder as if it
    were meaningful data."""
    view, _ = _make_view(tmp_path)
    patcher, _ = _attach_mock_page(view)
    chronicle = Chronicle(title="Some Chronicle")
    fake_event = MagicMock(control=MagicMock(data=chronicle))

    try:
        await view.edit_clicked(fake_event)
    finally:
        patcher.stop()

    assert view.edit_kind.value == ""


@pytest.mark.asyncio
async def test_save_edit_clicked_persists_changes(tmp_path):
    chronicle_service = AsyncMock()
    existing = Chronicle(title="Old Title", kind="Unknown")
    chronicle_service.get_chronicle.return_value = existing
    view, _ = _make_view(tmp_path, chronicle_service=chronicle_service)
    patcher, _ = _attach_mock_page(view)
    view.editing_chronicle_id = existing.id
    view.edit_title.value = "New Title"
    view.edit_description.value = "New description"
    view.edit_kind.value = "Meeting"
    view.edit_duration.value = "45m"

    try:
        await view.save_edit_clicked(MagicMock())
    finally:
        patcher.stop()

    chronicle_service.update_chronicle.assert_awaited_once()
    (saved,), _ = chronicle_service.update_chronicle.call_args
    assert saved.title == "New Title"
    assert saved.description == "New description"
    assert saved.kind == "Meeting"
    assert saved.duration == "45m"
    view.show_snackbar.assert_called_once()
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_edit_clicked_handles_deleted_chronicle(tmp_path):
    chronicle_service = AsyncMock()
    chronicle_service.get_chronicle.return_value = None
    view, _ = _make_view(tmp_path, chronicle_service=chronicle_service)
    patcher, _ = _attach_mock_page(view)
    view.editing_chronicle_id = uuid4()

    try:
        await view.save_edit_clicked(MagicMock())
    finally:
        patcher.stop()

    chronicle_service.update_chronicle.assert_not_awaited()
    view.show_snackbar.assert_called_once()


@pytest.mark.asyncio
async def test_delete_clicked_deletes_when_confirmed(tmp_path):
    chronicle_service = AsyncMock()
    view, _ = _make_view(tmp_path, chronicle_service=chronicle_service)
    view._confirm = AsyncMock(return_value=True)
    chronicle = Chronicle(title="Doomed")
    fake_event = MagicMock(control=MagicMock(data=chronicle))

    await view.delete_clicked(fake_event)

    chronicle_service.delete_chronicle.assert_awaited_once_with(chronicle.id)
    view.show_snackbar.assert_called_once()
    view.load_chronicles.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_clicked_does_nothing_when_cancelled(tmp_path):
    chronicle_service = AsyncMock()
    view, _ = _make_view(tmp_path, chronicle_service=chronicle_service)
    view._confirm = AsyncMock(return_value=False)
    chronicle = Chronicle(title="Safe")
    fake_event = MagicMock(control=MagicMock(data=chronicle))

    await view.delete_clicked(fake_event)

    chronicle_service.delete_chronicle.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_resolves_from_button_click(tmp_path):
    """Exercises the real show_dialog()/pop_dialog() mechanism, same as
    _ask_overwrite_or_append - see that dialog's regression note for why this
    matters (removing a dialog before the client confirms its close animation
    finished leaves it visually stuck open)."""
    view, _ = _make_view(tmp_path)
    patcher, mock_page = _attach_mock_page(view)

    try:
        task = asyncio.ensure_future(view._confirm("Delete chronicle?", "Are you sure?"))
        await asyncio.sleep(0)

        mock_page.show_dialog.assert_called_once()
        (dialog,), _ = mock_page.show_dialog.call_args
        confirm_button = dialog.actions[1]
        assert confirm_button.content == "Delete"
        await confirm_button.on_click(MagicMock())

        result = await asyncio.wait_for(task, timeout=1)
    finally:
        patcher.stop()

    assert result is True
    mock_page.pop_dialog.assert_called_once()


@pytest.mark.asyncio
async def test_import_audio_clicked_reads_chronicle_id_from_event_control_data(tmp_path):
    view, _ = _make_view(tmp_path)
    view.pick_file = AsyncMock()
    chronicle_id = uuid4()
    fake_event = MagicMock(control=MagicMock(data=chronicle_id))

    await view.import_audio_clicked(fake_event)

    assert view.current_chronicle_id == chronicle_id
    assert view.picker_action == "AUDIO"
    view.pick_file.assert_awaited_once()


def test_dark_mode_flag_changes_card_colors(tmp_path):
    """Regression test: ArchiveView used to hardcode BLUE_GREY_800/700 card colors
    regardless of the dark_mode setting, so toggling to light mode left every card
    looking exactly as dark as before. dark_mode must actually reach the colors used
    to build a card.
    """
    dark_view, _ = _make_view(tmp_path)
    light_view = ArchiveView(
        AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), dark_mode=False
    )
    chronicle = Chronicle(title="Some Chronicle")

    dark_card = dark_view.create_chronicle_card(chronicle)
    light_card = light_view.create_chronicle_card(chronicle)

    assert dark_card.bgcolor != light_card.bgcolor


def test_show_snackbar_uses_page_show_dialog(tmp_path):
    """Regression test: ft.Page has no `snack_bar` attribute in flet 0.86.4 - a
    SnackBar is shown via page.show_dialog(), the same mechanism as ft.AlertDialog."""
    view, _ = _make_view(tmp_path)
    view.show_snackbar = ArchiveView.show_snackbar.__get__(view)  # undo the test stub
    mock_page = MagicMock(spec=ft.Page)

    with patch.object(ArchiveView, "page", new_callable=PropertyMock) as page_prop:
        page_prop.return_value = mock_page
        view.show_snackbar("Something happened")

    mock_page.show_dialog.assert_called_once()
    (dialog,), _ = mock_page.show_dialog.call_args
    assert isinstance(dialog, ft.SnackBar)
