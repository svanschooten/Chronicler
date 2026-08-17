from enum import Enum

from chronicler.core.models import Chronicle


class ViewType(str, Enum):
    ARCHIVE = "archive"
    TASKS = "tasks"
    SETTINGS = "settings"
    TRANSCRIPT = "transcript"

    @classmethod
    def from_nav_id(cls, view_id: str) -> "ViewType | None":
        """Maps a sidebar nav id to its view, or None for an id the sidebar doesn't
        offer. TRANSCRIPT is deliberately reachable this way too - it has no sidebar
        entry, but rejecting it here would be a lie about what the enum contains."""
        try:
            return cls(view_id)
        except ValueError:
            return None


class AppState:
    """Which view is on screen and, for the transcript view, which chronicle it's
    showing."""

    def __init__(self) -> None:
        self.current_view: ViewType = ViewType.ARCHIVE
        self.selected_chronicle: Chronicle | None = None

    def navigate_to(self, view: ViewType, chronicle: Chronicle | None = None) -> None:
        self.current_view = view
        self.selected_chronicle = chronicle
