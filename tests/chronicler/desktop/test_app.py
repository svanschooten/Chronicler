from chronicler.desktop.app import AppState, ViewType


def test_app_initial_state():
    state = AppState()
    assert state.current_view == ViewType.ARCHIVE


def test_app_navigation():
    state = AppState()
    state.navigate_to(ViewType.TASKS)
    assert state.current_view == ViewType.TASKS
