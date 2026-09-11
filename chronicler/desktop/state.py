from dataclasses import dataclass
from enum import Enum

from chronicler.core.models import Chronicle


@dataclass(frozen=True)
class ModelCheck:
    """
    What the service layer answered when last asked about language models.

    The settings page needs the answer as a value it can show, and the app needs it as
    state the views are built from, so the refresh returns it rather than only storing it.
    """

    models: list[str]
    error: str | None = None

    @property
    def reachable(self) -> bool:
        return self.error is None


class ViewType(str, Enum):
    ARCHIVE = "archive"
    TASKS = "tasks"
    SETTINGS = "settings"
    TRANSCRIPT = "transcript"

    @classmethod
    def from_nav_id(cls, view_id: str) -> "ViewType | None":
        """Maps a sidebar nav id to its view, or None for an id the sidebar doesn't offer."""
        try:
            return cls(view_id)
        except ValueError:
            return None


class AppState:
    """Which view is on screen and, for the transcript view, which chronicle it's showing."""

    def __init__(self) -> None:
        self.current_view: ViewType = ViewType.ARCHIVE
        self.selected_chronicle: Chronicle | None = None

    def navigate_to(self, view: ViewType, chronicle: Chronicle | None = None) -> None:
        self.current_view = view
        self.selected_chronicle = chronicle
