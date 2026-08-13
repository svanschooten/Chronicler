from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from chronicler.core.file_staging import stage_local_file
from chronicler.core.models import Chronicle
from chronicler.desktop.views.archive import ArchiveView


def _make_view(tmp_path, chronicle_service=None, task_service=None):
    imports_dir = tmp_path / "workspace" / "imports"
    imports_dir.mkdir(parents=True)

    async def stage_file(local_path: str) -> str:
        return str(stage_local_file(Path(local_path), imports_dir))

    view = ArchiveView(
        chronicle_service or AsyncMock(),
        task_service or AsyncMock(),
        AsyncMock(),
        stage_file,
    )
    # ArchiveView isn't attached to a live Flet Page in this unit test (Control.page
    # walks the parent chain and raises if not found) - these two only touch page/UI
    # refresh, not the staging behavior under test, so stub them out.
    view.show_snackbar = MagicMock()
    view.load_chronicles = AsyncMock()
    return view, imports_dir


@pytest.mark.asyncio
async def test_handle_file_result_stages_audio_import_outside_workspace(tmp_path):
    picked_file = tmp_path / "Downloads" / "recording.mp3"
    picked_file.parent.mkdir(parents=True)
    picked_file.write_text("fake audio")

    task_service = AsyncMock()
    view, imports_dir = _make_view(tmp_path, task_service=task_service)
    view.picker_action = "AUDIO"
    chronicle_id = uuid4()
    view.current_chronicle_id = chronicle_id
    view.chronicle_list = MagicMock()

    await view.handle_file_result(str(picked_file))

    # handle_file_result resets current_chronicle_id to None in its finally block, so
    # compare against the value captured before the call.
    task_service.queue_import.assert_awaited_once()
    queued_chronicle_id, queued_path = task_service.queue_import.call_args.args
    assert queued_chronicle_id == chronicle_id
    assert Path(queued_path).resolve().is_relative_to(imports_dir.resolve())
    assert Path(queued_path).name != "recording.mp3"


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
