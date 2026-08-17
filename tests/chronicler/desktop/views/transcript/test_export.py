"""Tests for TranscriptExporter - the Export menu and save flow.

What the exported text actually looks like is covered by
tests/chronicler/core/services/test_transcript_export.py; this is about the menu, the
save dialog and writing the file.
"""

from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.views.transcript.export import TranscriptExporter


@pytest.fixture
def make_exporter():
    def _make(chronicle=None, transcript_service=None, file_picker=None):
        picker = AsyncMock() if file_picker is None else file_picker
        exporter = TranscriptExporter(
            chronicle or Chronicle(title="Some Chronicle"),
            transcript_service or AsyncMock(),
            MagicMock(),
            lambda: picker,
        )
        return exporter, picker

    return _make


def _event(data=False):
    return MagicMock(control=MagicMock(data=data))


def test_menu_offers_plain_text_now_and_signposts_the_rest():
    exporter = TranscriptExporter(Chronicle(title="T"), AsyncMock(), MagicMock(), lambda: None)

    menu = exporter.menu()

    enabled = [item for item in menu.items if not item.disabled]
    disabled = [item for item in menu.items if item.disabled]
    assert len(enabled) == 2
    assert [item.data for item in enabled] == [False, True]
    # HTML, PDF and .zip are planned, not built - offered but disabled rather than
    # silently absent.
    assert len(disabled) == 3


@pytest.mark.asyncio
async def test_export_writes_the_rendered_transcript_to_the_chosen_file(
    make_exporter, tmp_path
):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "Alice: hi\nBob: hello"
    exporter, picker = make_exporter(transcript_service=transcript_service)
    destination = tmp_path / "export.txt"
    picker.save_file.return_value = str(destination)

    await exporter.export_plaintext_clicked(_event(data=False))

    assert destination.read_text() == "Alice: hi\nBob: hello"
    transcript_service.export_plaintext.assert_awaited_once_with(
        exporter.chronicle.id, include_timestamps=False
    )


@pytest.mark.asyncio
async def test_export_with_timestamps_passes_the_flag_and_marks_the_filename(
    make_exporter, tmp_path
):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "[00:00:05] Alice: hi"
    exporter, picker = make_exporter(transcript_service=transcript_service)
    picker.save_file.return_value = str(tmp_path / "export.txt")

    await exporter.export_plaintext_clicked(_event(data=True))

    transcript_service.export_plaintext.assert_awaited_once_with(
        exporter.chronicle.id, include_timestamps=True
    )
    assert picker.save_file.call_args.kwargs["file_name"].endswith("_timestamps.txt")


@pytest.mark.asyncio
async def test_export_does_nothing_when_the_save_dialog_is_cancelled(make_exporter, tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "Alice: hi"
    exporter, picker = make_exporter(transcript_service=transcript_service)
    picker.save_file.return_value = None

    await exporter.export_plaintext_clicked(_event())

    exporter.show_snackbar.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_export_reports_a_service_failure_without_opening_the_save_dialog(
    make_exporter,
):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.side_effect = RuntimeError("boom")
    exporter, picker = make_exporter(transcript_service=transcript_service)

    await exporter.export_plaintext_clicked(_event())

    picker.save_file.assert_not_called()
    assert "boom" in exporter.show_snackbar.call_args.args[0]


@pytest.mark.asyncio
async def test_export_reports_a_write_failure(make_exporter, tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "text"
    exporter, picker = make_exporter(transcript_service=transcript_service)
    # A directory path can't be opened for writing.
    picker.save_file.return_value = str(tmp_path)

    await exporter.export_plaintext_clicked(_event())

    assert "Error writing export file" in exporter.show_snackbar.call_args.args[0]


@pytest.mark.asyncio
async def test_export_reports_when_there_is_no_picker_yet(make_exporter):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "text"
    exporter, _ = make_exporter(transcript_service=transcript_service, file_picker=None)
    exporter._file_picker = lambda: None

    await exporter.export_plaintext_clicked(_event())

    exporter.show_snackbar.assert_called_once_with("File picker not available.")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Weekly product sync", "Weekly product sync"),
        ("D&D: Session #3 / Recap", "D_D_ Session _3 _ Recap"),
        ("///", "___"),
        ("", "transcript"),
    ],
)
def test_default_file_stem_strips_path_unsafe_characters(title, expected):
    exporter = TranscriptExporter(
        Chronicle(title=title), AsyncMock(), MagicMock(), lambda: None
    )

    assert exporter.default_file_stem() == expected


@pytest.mark.asyncio
async def test_export_suggests_a_filename_with_no_path_separators(make_exporter, tmp_path):
    transcript_service = AsyncMock()
    transcript_service.export_plaintext.return_value = "text"
    exporter, picker = make_exporter(
        chronicle=Chronicle(title="D&D: Session #3 / Recap"),
        transcript_service=transcript_service,
    )
    picker.save_file.return_value = str(tmp_path / "out.txt")

    await exporter.export_plaintext_clicked(_event())

    file_name = picker.save_file.call_args.kwargs["file_name"]
    assert "/" not in file_name
    assert file_name.endswith(".txt")
    assert picker.save_file.call_args.kwargs["file_type"] == ft.FilePickerFileType.CUSTOM
