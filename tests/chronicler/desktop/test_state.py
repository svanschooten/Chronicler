"""Tests for AppState and ViewType."""

from chronicler.core.models import Chronicle
from chronicler.desktop.state import AppState, ViewType


def test_the_archive_is_the_initial_view():
    assert AppState().current_view == ViewType.ARCHIVE
    assert AppState().selected_chronicle is None


def test_navigate_to_changes_the_current_view():
    state = AppState()

    state.navigate_to(ViewType.TASKS)

    assert state.current_view == ViewType.TASKS


def test_navigate_to_carries_the_selected_chronicle():
    state = AppState()
    chronicle = Chronicle(title="Weekly product sync")

    state.navigate_to(ViewType.TRANSCRIPT, chronicle)

    assert state.selected_chronicle is chronicle


def test_navigating_away_clears_the_selected_chronicle():
    """Otherwise a stale selection outlives the transcript view that used it, and a
    later navigation back to TRANSCRIPT would render whatever was last open."""
    state = AppState()
    state.navigate_to(ViewType.TRANSCRIPT, Chronicle(title="T"))

    state.navigate_to(ViewType.ARCHIVE)

    assert state.selected_chronicle is None


def test_from_nav_id_maps_every_sidebar_entry():
    assert ViewType.from_nav_id("archive") is ViewType.ARCHIVE
    assert ViewType.from_nav_id("tasks") is ViewType.TASKS
    assert ViewType.from_nav_id("settings") is ViewType.SETTINGS


def test_from_nav_id_returns_none_for_an_unknown_id():
    assert ViewType.from_nav_id("nope") is None
    assert ViewType.from_nav_id("") is None
