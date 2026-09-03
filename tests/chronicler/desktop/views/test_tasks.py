from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import flet as ft
import pytest

from chronicler.core.models import Chronicle, Task, TaskStatus, TaskType
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.tasks import TasksView
from tests.chronicler.desktop.controls import find_controls, text_values


@pytest.fixture
def make_view():
    def _make(task_service=None, chronicle_service=None, chronicles=None, **kwargs):
        if chronicle_service is None:
            chronicle_service = AsyncMock()
            chronicle_service.list_chronicles.return_value = chronicles or []
        view = TasksView(task_service or AsyncMock(), chronicle_service, **kwargs)
        view.update = MagicMock()
        return view

    return _make


def _info_column(row):
    """The type/subtitle/timestamps column of a task row."""
    return row.content.controls[1]


def _timestamps_text(row) -> str:
    return _info_column(row).controls[2].value


def _retry_buttons(row) -> list[ft.IconButton]:
    return [
        c
        for c in find_controls(row, lambda c: isinstance(c, ft.IconButton))
        if getattr(c, "tooltip", None) == "Run this task again"
    ]


def test_hide_completed_defaults_to_true(make_view):
    assert make_view().hide_completed is True


def test_dark_mode_flag_changes_task_row_colors(make_view):
    """
    Regression test: TasksView used to hardcode BLUE_GREY_700/600 regardless of dark_mode,
    so task rows stayed dark-styled even after switching to light mode.
    """
    dark_view = make_view(dark_mode=True)
    light_view = make_view(dark_mode=False)
    task = Task(type=TaskType.IMPORT, status=TaskStatus.WORKING)

    assert dark_view.create_task_row(task).bgcolor != light_view.create_task_row(task).bgcolor
    assert dark_view.colors == theme_colors(True)
    assert light_view.colors == theme_colors(False)


def test_task_row_shows_only_created_for_pending_task(make_view):
    task = Task(type=TaskType.IMPORT, status=TaskStatus.PENDING, created_at=datetime(2026, 1, 1))

    text = _timestamps_text(make_view().create_task_row(task))

    assert "Created 2026-01-01" in text
    assert "Started" not in text
    assert "Completed" not in text


def test_task_row_shows_created_and_started_for_working_task(make_view):
    task = Task(
        type=TaskType.IMPORT,
        status=TaskStatus.WORKING,
        created_at=datetime(2026, 1, 1),
        claimed_at=datetime(2026, 1, 1, 12, 30),
    )

    text = _timestamps_text(make_view().create_task_row(task))

    assert "Created 2026-01-01" in text
    assert "Started 2026-01-01 12:30" in text
    assert "Completed" not in text


@pytest.mark.parametrize("status", [TaskStatus.DONE, TaskStatus.FAILED])
def test_task_row_shows_completed_for_terminal_task(make_view, status):
    task = Task(
        type=TaskType.IMPORT,
        status=status,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1, 12, 45),
    )

    assert "Completed 2026-01-01 12:45" in _timestamps_text(make_view().create_task_row(task))


@pytest.mark.asyncio
async def test_task_row_names_the_chronicle_it_belongs_to(make_view):
    """
    A row used to show only its type and status, so a queue of several tasks gave no
    indication of which chronicle each one was for.
    """
    chronicle = Chronicle(title="Weekly product sync")
    task = Task(type=TaskType.IMPORT, status=TaskStatus.PENDING, chronicle_id=chronicle.id)
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [task]
    view = make_view(task_service=task_service, chronicles=[chronicle])

    await view.load_tasks()

    assert "Weekly product sync · Status: PENDING" in text_values(view.task_list.controls[0])


@pytest.mark.asyncio
async def test_row_falls_back_to_status_alone_for_an_unknown_chronicle(make_view):
    """A task whose chronicle has since been deleted must still render."""
    task = Task(type=TaskType.IMPORT, status=TaskStatus.PENDING, chronicle_id=uuid4())
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [task]
    view = make_view(task_service=task_service, chronicles=[])

    await view.load_tasks()

    assert "Status: PENDING" in text_values(view.task_list.controls[0])


def test_row_falls_back_to_status_alone_for_a_task_with_no_chronicle(make_view):
    task = Task(type=TaskType.IMPORT, status=TaskStatus.PENDING)

    assert _info_column(make_view().create_task_row(task)).controls[1].value == "Status: PENDING"


@pytest.mark.asyncio
async def test_a_failure_to_resolve_titles_does_not_fail_the_whole_view(make_view):
    chronicle_service = AsyncMock()
    chronicle_service.list_chronicles.side_effect = RuntimeError("archive unreachable")
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [Task(type=TaskType.IMPORT, chronicle_id=uuid4())]
    view = make_view(task_service=task_service, chronicle_service=chronicle_service)

    await view.load_tasks()

    assert len(view.task_list.controls) == 1
    assert "Status: PENDING" in text_values(view.task_list.controls[0])


@pytest.mark.asyncio
async def test_titles_are_resolved_once_per_load_not_once_per_row(make_view):
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [
        Task(type=TaskType.IMPORT, chronicle_id=uuid4()) for _ in range(5)
    ]
    chronicle_service = AsyncMock()
    chronicle_service.list_chronicles.return_value = []
    view = make_view(task_service=task_service, chronicle_service=chronicle_service)

    await view.load_tasks()

    chronicle_service.list_chronicles.assert_awaited_once()


def test_a_failed_task_shows_its_error(make_view):
    task = Task(
        type=TaskType.IMPORT, status=TaskStatus.FAILED, error="file_path must be inside imports"
    )

    assert "file_path must be inside imports" in text_values(make_view().create_task_row(task))


def test_a_pending_task_shows_no_error_row(make_view):
    task = Task(type=TaskType.IMPORT, status=TaskStatus.PENDING)

    assert len(_info_column(make_view().create_task_row(task)).controls) == 3


@pytest.mark.parametrize(
    ("status", "icon"),
    [
        (TaskStatus.DONE, ft.Icons.CHECK_CIRCLE),
        (TaskStatus.FAILED, ft.Icons.ERROR_OUTLINE),
        (TaskStatus.PENDING, ft.Icons.PENDING_ACTIONS),
        (TaskStatus.WORKING, ft.Icons.PENDING_ACTIONS),
    ],
)
def test_status_icon_distinguishes_failure_from_success(make_view, status, icon):
    """FAILED used to share PENDING's icon, so a failed task looked like a queued one."""
    row = make_view().create_task_row(Task(type=TaskType.IMPORT, status=status))

    assert row.content.controls[0].icon == icon


def test_only_a_working_task_gets_a_progress_bar(make_view):
    working = make_view().create_task_row(
        Task(type=TaskType.IMPORT, status=TaskStatus.WORKING, progress=40)
    )
    pending = make_view().create_task_row(Task(type=TaskType.IMPORT, status=TaskStatus.PENDING))

    assert find_controls(working, lambda c: isinstance(c, ft.ProgressBar))
    assert not find_controls(pending, lambda c: isinstance(c, ft.ProgressBar))


@pytest.mark.parametrize("status", [TaskStatus.FAILED, TaskStatus.DONE])
def test_finished_tasks_offer_a_retry_button_carrying_the_task_id(make_view, status):
    task = Task(type=TaskType.IMPORT, status=status)

    (button,) = _retry_buttons(make_view().create_task_row(task))

    assert button.data == task.id
    assert button.on_click is not None


@pytest.mark.parametrize("status", [TaskStatus.PENDING, TaskStatus.WORKING])
def test_unfinished_tasks_offer_no_retry_button(make_view, status):
    """
    A WORKING task is already running - re-queueing it would let a second worker claim it
    while the first is still going.
    """
    task = Task(type=TaskType.IMPORT, status=status)

    assert _retry_buttons(make_view().create_task_row(task)) == []


@pytest.mark.asyncio
async def test_retry_clicked_requeues_the_task_and_reloads(make_view):
    task_service = AsyncMock()
    view = make_view(task_service=task_service)
    view.show_snackbar = MagicMock()
    view.load_tasks = AsyncMock()
    task_id = uuid4()

    await view.retry_clicked(MagicMock(control=MagicMock(data=task_id)))

    task_service.retry_task.assert_awaited_once_with(task_id)
    view.show_snackbar.assert_called_once()
    view.load_tasks.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_tasks_hides_done_tasks_by_default(make_view):
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [
        Task(type=TaskType.IMPORT, status=TaskStatus.DONE),
        Task(type=TaskType.IMPORT, status=TaskStatus.WORKING),
    ]
    view = make_view(task_service=task_service)

    await view.load_tasks()

    assert len(view.task_list.controls) == 1


@pytest.mark.asyncio
async def test_load_tasks_shows_done_tasks_when_unhidden(make_view):
    task_service = AsyncMock()
    task_service.list_tasks.return_value = [
        Task(type=TaskType.IMPORT, status=TaskStatus.DONE),
        Task(type=TaskType.IMPORT, status=TaskStatus.WORKING),
    ]
    view = make_view(task_service=task_service)
    view.hide_completed = False

    await view.load_tasks()

    assert len(view.task_list.controls) == 2


@pytest.mark.asyncio
async def test_search_changed_switches_to_searching(make_view):
    task_service = AsyncMock()
    task_service.search_tasks.return_value = []
    view = make_view(task_service=task_service)

    await view.search_changed(MagicMock(data="IMPORT"))

    assert view.query == "IMPORT"
    task_service.search_tasks.assert_awaited_once_with("IMPORT")
    task_service.list_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_tasks_shows_a_placeholder_when_there_are_none(make_view):
    task_service = AsyncMock()
    task_service.list_tasks.return_value = []
    view = make_view(task_service=task_service)

    await view.load_tasks()

    assert "No tasks yet." in view.task_list.controls[0].value


@pytest.mark.asyncio
async def test_load_tasks_reports_a_service_failure_in_place(make_view):
    task_service = AsyncMock()
    task_service.list_tasks.side_effect = RuntimeError("queue unreachable")
    view = make_view(task_service=task_service)

    await view.load_tasks()

    assert "queue unreachable" in view.task_list.controls[0].value
