from unittest.mock import MagicMock, PropertyMock, patch

import flet as ft
import pytest


@pytest.fixture
def attach_page():
    """Gives a Flet control a stand-in `page` for the duration of one test."""
    patchers = []

    def _attach(control_cls: type) -> MagicMock:
        mock_page = MagicMock(spec=ft.Page)
        patcher = patch.object(control_cls, "page", new_callable=PropertyMock)
        page_property = patcher.start()
        patchers.append(patcher)
        page_property.return_value = mock_page
        return mock_page

    yield _attach

    for patcher in patchers:
        patcher.stop()
