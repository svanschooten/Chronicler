import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.views.transcript import TranscriptView


def _make_view(chronicle=None, transcript_service=None, task_service=None):
    view = TranscriptView(
        chronicle or Chronicle(title="Some Chronicle"),
        AsyncMock(),
        transcript_service or AsyncMock(),
        task_service or AsyncMock(),
    )
    view.file_picker = AsyncMock()
    return view


def _attach_mock_page(view):
    """TranscriptView isn't attached to a live Flet Page in these unit tests -
    `page` is a read-only property (walks the parent chain, raises if unattached),
    so it can't be assigned directly; patch the class attribute instead.
    """
    mock_page = MagicMock(spec=ft.Page)
    patcher = patch.object(TranscriptView, "page", new_callable=PropertyMock)
    page_prop = patcher.start()
    page_prop.return_value = mock_page
    return patcher, mock_page


@pytest.mark.asyncio
async def test_export_plaintext_clicked_writes_chosen_file(tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "Alice: hi\nBob: hello"
    view = _make_view(transcript_service=transcript_service)
    patcher, _ = _attach_mock_page(view)
    destination = tmp_path / "export.txt"
    view.file_picker.save_file.return_value = str(destination)
    fake_event = MagicMock(control=MagicMock(data=False))

    try:
        await view.export_plaintext_clicked(fake_event)
    finally:
        patcher.stop()

    assert destination.read_text() == "Alice: hi\nBob: hello"
    transcript_service.export_plaintext.assert_awaited_once_with(
        view.chronicle.id, include_timestamps=False
    )


@pytest.mark.asyncio
async def test_export_plaintext_clicked_with_timestamps_flag(tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "[00:00:05] Alice: hi"
    view = _make_view(transcript_service=transcript_service)
    patcher, _ = _attach_mock_page(view)
    destination = tmp_path / "export.txt"
    view.file_picker.save_file.return_value = str(destination)
    fake_event = MagicMock(control=MagicMock(data=True))

    try:
        await view.export_plaintext_clicked(fake_event)
    finally:
        patcher.stop()

    transcript_service.export_plaintext.assert_awaited_once_with(
        view.chronicle.id, include_timestamps=True
    )
    save_kwargs = view.file_picker.save_file.call_args.kwargs
    assert save_kwargs["file_name"].endswith("_timestamps.txt")


@pytest.mark.asyncio
async def test_export_plaintext_clicked_does_nothing_when_save_dialog_cancelled(tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "Alice: hi"
    view = _make_view(transcript_service=transcript_service)
    patcher, mock_page = _attach_mock_page(view)
    view.file_picker.save_file.return_value = None

    try:
        await view.export_plaintext_clicked(MagicMock())
    finally:
        patcher.stop()

    mock_page.show_dialog.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_export_plaintext_clicked_shows_error_on_service_failure(tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.side_effect = RuntimeError("boom")
    view = _make_view(transcript_service=transcript_service)
    patcher, mock_page = _attach_mock_page(view)

    try:
        await view.export_plaintext_clicked(MagicMock())
    finally:
        patcher.stop()

    view.file_picker.save_file.assert_not_called()
    mock_page.show_dialog.assert_called_once()
    (dialog,), _ = mock_page.show_dialog.call_args
    assert isinstance(dialog, ft.SnackBar)


@pytest.mark.asyncio
async def test_export_plaintext_clicked_uses_sanitized_chronicle_title_as_filename(tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "text"
    view = _make_view(
        chronicle=Chronicle(title="D&D: Session #3 / Recap"),
        transcript_service=transcript_service,
    )
    patcher, _ = _attach_mock_page(view)
    view.file_picker.save_file.return_value = str(tmp_path / "out.txt")

    try:
        await view.export_plaintext_clicked(MagicMock())
    finally:
        patcher.stop()

    kwargs = view.file_picker.save_file.call_args.kwargs
    assert "/" not in kwargs["file_name"]
    assert kwargs["file_name"].endswith(".txt")


def test_did_mount_registers_file_picker_as_service_not_overlay():
    """Regression test: FilePicker is a Service (flet.controls.services.service),
    not a visual control - the client fails with "Unknown control: FilePicker" if
    it's added to page.overlay (which expects renderable widgets). It must be
    registered through page.services instead. Built directly (not via _make_view,
    which pre-stubs file_picker) so did_mount actually exercises the real
    `if self.file_picker is None` construction path.
    """
    view = TranscriptView(
        Chronicle(title="Some Chronicle"), AsyncMock(), AsyncMock(), AsyncMock()
    )
    patcher, mock_page = _attach_mock_page(view)
    mock_page.overlay = []
    mock_page.services = []

    try:
        view.did_mount()
    finally:
        patcher.stop()

    assert view.file_picker is not None
    assert view.file_picker in mock_page.services
    assert view.file_picker not in mock_page.overlay


@pytest.mark.asyncio
async def test_load_transcript_shows_placeholder_when_empty():
    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = []
    view = _make_view(transcript_service=transcript_service)
    view.transcript_area.update = MagicMock()

    await view.load_transcript()

    assert view.transcript_area.value == "Transcript is empty or still processing."


@pytest.mark.asyncio
async def test_load_transcript_hides_timestamps_by_default():
    from chronicler.core.models import TranscriptLine

    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(speaker_name="Alice", text="Hi", start_time=65.0, end_time=66.0)
    ]
    view = _make_view(transcript_service=transcript_service)
    view.transcript_area.update = MagicMock()

    await view.load_transcript()

    assert view.transcript_area.value == "Alice: Hi"


@pytest.mark.asyncio
async def test_show_timestamps_changed_reformats_without_refetching():
    from chronicler.core.models import TranscriptLine

    transcript_service = AsyncMock()
    transcript_service.get_transcript.return_value = [
        TranscriptLine(speaker_name="Alice", text="Hi", start_time=65.0, end_time=66.0)
    ]
    view = _make_view(transcript_service=transcript_service)
    view.transcript_area.update = MagicMock()
    await view.load_transcript()
    transcript_service.get_transcript.reset_mock()

    fake_event = MagicMock(control=MagicMock(value=True))
    await view.show_timestamps_changed(fake_event)

    assert view.transcript_area.value == "[00:01:05] Alice: Hi"
    transcript_service.get_transcript.assert_not_awaited()

    fake_event.control.value = False
    await view.show_timestamps_changed(fake_event)

    assert view.transcript_area.value == "Alice: Hi"


@pytest.mark.asyncio
async def test_load_sources_shows_placeholder_when_empty():
    transcript_service = AsyncMock()
    transcript_service.list_audio_sources.return_value = []
    view = _make_view(transcript_service=transcript_service)
    view.sources_list.update = MagicMock()

    await view.load_sources()

    assert len(view.sources_list.controls) == 1
    assert "No audio sources" in view.sources_list.controls[0].value


@pytest.mark.asyncio
async def test_load_sources_lists_a_row_per_source():
    transcript_service = AsyncMock()
    transcript_service.list_audio_sources.return_value = [
        "/workspace/chronicles/x/sources/alice.mp3",
        "/workspace/chronicles/x/sources/bob.mp3",
    ]
    view = _make_view(transcript_service=transcript_service)
    view.sources_list.update = MagicMock()

    await view.load_sources()

    assert len(view.sources_list.controls) == 2


@pytest.mark.asyncio
async def test_transcribe_source_clicked_queues_task_with_chosen_speaker():
    task_service = AsyncMock()
    view = _make_view(task_service=task_service)
    patcher, _ = _attach_mock_page(view)
    view._ask_speaker_name = AsyncMock(return_value="Alice")
    fake_event = MagicMock(control=MagicMock(data="/sources/alice.mp3"))

    try:
        await view.transcribe_source_clicked(fake_event)
    finally:
        patcher.stop()

    task_service.queue_transcribe.assert_awaited_once_with(
        view.chronicle.id, "/sources/alice.mp3", "Alice"
    )


@pytest.mark.asyncio
async def test_transcribe_source_clicked_does_nothing_when_cancelled():
    task_service = AsyncMock()
    view = _make_view(task_service=task_service)
    view._ask_speaker_name = AsyncMock(return_value=None)
    fake_event = MagicMock(control=MagicMock(data="/sources/alice.mp3"))

    await view.transcribe_source_clicked(fake_event)

    task_service.queue_transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_speaker_name_resolves_from_button_click():
    transcript_service = AsyncMock()
    transcript_service.list_speaker_names.return_value = ["Alice"]
    view = _make_view(transcript_service=transcript_service)
    patcher, mock_page = _attach_mock_page(view)

    try:
        task = asyncio.ensure_future(view._ask_speaker_name("alice.mp3"))
        await asyncio.sleep(0)

        mock_page.show_dialog.assert_called_once()
        (dialog,), _ = mock_page.show_dialog.call_args
        speaker_field = dialog.content.controls[1]
        speaker_field.value = "Bob"
        transcribe_button = dialog.actions[1]
        assert transcribe_button.content == "Transcribe"
        await transcribe_button.on_click(MagicMock())

        result = await asyncio.wait_for(task, timeout=1)
    finally:
        patcher.stop()

    assert result == "Bob"
    mock_page.pop_dialog.assert_called_once()
