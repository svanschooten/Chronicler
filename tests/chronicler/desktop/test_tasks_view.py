from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler.core.models import Task, TaskStatus, TaskType
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.tasks import TasksView


def _timestamps_text(row) -> str:
    info_column = row.content.controls[1]
    return info_column.controls[2].value


def _make_view(task_service=None):
    view = TasksView(task_service or AsyncMock())
    # TasksView isn't attached to a live Flet Page in this unit test - update() just
    # needs to not raise (Control.update requires self.page, which is unavailable here).
    view.update = MagicMock()
    return view


def test_hide_completed_defaults_to_true():
    view = _make_view()
    assert view.hide_completed is True


def test_dark_mode_flag_changes_task_row_colors():
    """Regression test: TasksView used to hardcode BLUE_GREY_700/600 regardless of
    dark_mode, so task rows stayed dark-styled even after switching to light mode."""
    dark_view = TasksView(AsyncMock(), dark_mode=True)
    light_view = TasksView(AsyncMock(), dark_mode=False)
    task = Task(type=TaskType.IMPORT, status=TaskStatus.WORKING)

    assert dark_view.create_task_row(task).bgcolor != light_view.create_task_row(task).bgcolor
    assert dark_view.colors == theme_colors(True)
    assert light_view.colors == theme_colors(False)


def test_task_row_shows_only_created_for_pending_task():
    view = _make_view()
    task = Task(type=TaskType.IMPORT, status=TaskStatus.PENDING, created_at=datetime(2026, 1, 1))

    text = _timestamps_text(view.create_task_row(task))

    assert "Created 2026-01-01" in text
    assert "Started" not in text
    assert "Completed" not in text


def test_task_row_shows_created_and_started_for_working_task():
    view = _make_view()
    task = Task(
        type=TaskType.IMPORT,
        status=TaskStatus.WORKING,
        created_at=datetime(2026, 1, 1),
        claimed_at=datetime(2026, 1, 1, 12, 30),
    )

    text = _timestamps_text(view.create_task_row(task))

    assert "Created 2026-01-01" in text
    assert "Started 2026-01-01 12:30" in text
    assert "Completed" not in text


def test_task_row_shows_completed_for_done_task():
    view = _make_view()
    task = Task(
        type=TaskType.IMPORT,
        status=TaskStatus.DONE,
        created_at=datetime(2026, 1, 1),
        claimed_at=datetime(2026, 1, 1, 12, 30),
        updated_at=datetime(2026, 1, 1, 12, 45),
    )

    text = _timestamps_text(view.create_task_row(task))

    assert "Completed 2026-01-01 12:45" in text


def test_task_row_shows_completed_for_failed_task():
    view = _make_view()
    task = Task(
        type=TaskType.IMPORT,
        status=TaskStatus.FAILED,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1, 12, 45),
    )

    text = _timestamps_text(view.create_task_row(task))

    assert "Completed 2026-01-01 12:45" in text


@pytest.mark.asyncio
async def test_load_tasks_hides_done_tasks_by_default():
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [
        Task(type=TaskType.IMPORT, status=TaskStatus.DONE),
        Task(type=TaskType.IMPORT, status=TaskStatus.WORKING),
    ]
    view = _make_view(task_service)

    await view.load_tasks()

    assert len(view.task_list.controls) == 1


@pytest.mark.asyncio
async def test_load_tasks_shows_done_tasks_when_unhidden():
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [
        Task(type=TaskType.IMPORT, status=TaskStatus.DONE),
        Task(type=TaskType.IMPORT, status=TaskStatus.WORKING),
    ]
    view = _make_view(task_service)
    view.hide_completed = False

    await view.load_tasks()

    assert len(view.task_list.controls) == 2
