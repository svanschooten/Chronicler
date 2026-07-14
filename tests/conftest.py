import pytest
from unittest.mock import MagicMock
import flet

@pytest.fixture(autouse=True)
def mock_flet_app(monkeypatch):
    # Mock both flet.app and flet.run as versions might vary
    monkeypatch.setattr(flet, "app", MagicMock())
    if hasattr(flet, "run"):
        monkeypatch.setattr(flet, "run", MagicMock())
