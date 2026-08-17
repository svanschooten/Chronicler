from unittest.mock import MagicMock, PropertyMock, patch

import flet as ft
import pytest


@pytest.fixture
def attach_page():
    """Gives a Flet control a stand-in `page` for the duration of one test.

    Controls under test here are never attached to a live Flet page, and `page` is a
    read-only property that walks the parent chain and raises when it finds none - so
    it can't simply be assigned. This patches it at the class level and unpatches on
    teardown, which every test that touches `self.page` used to hand-roll in its own
    try/finally.

    Usage: `page = attach_page(ArchiveView)` - the returned MagicMock is what
    `view.page` resolves to.
    """
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
