"""Dialogs close when they should, and leave the view working behind them."""

import flet as ft
import pytest

from chronicler.i18n import t
from tests.ui.conftest import CHRONICLE_TITLE
from tests.ui.test_views import tap_once

pytestmark = pytest.mark.asyncio


async def test_cancelling_the_create_form_closes_it(tester):
    await tap_once(tester, await tester.find_by_text(t("archive.new")))
    assert (await tester.find_by_text(t("forms.create_title"))).count == 1

    await tap_once(tester, await tester.find_by_text(t("common.cancel")))

    assert (await tester.find_by_text(t("forms.create_title"))).count == 0


async def test_a_dismissed_confirmation_does_not_block_the_next_one(tester):
    """Ticket 073: a dialog closed by clicking outside it used to leave its action waiting."""
    delete = await tester.find_by_tooltip(t("actions.delete"))
    await tap_once(tester, delete)
    assert (await tester.find_by_text(t("actions.delete_title"))).count == 1

    await tester.tap_at(ft.Offset(5, 5))
    await tester.pump_and_settle()
    assert (await tester.find_by_text(t("actions.delete_title"))).count == 0
    assert (await tester.find_by_text(CHRONICLE_TITLE)).count == 1

    await tap_once(tester, await tester.find_by_tooltip(t("actions.delete")))
    await tap_once(tester, await tester.find_by_text(t("common.delete")))

    assert (await tester.find_by_text(CHRONICLE_TITLE)).count == 0
    assert (await tester.find_by_text(t("archive.empty"))).count == 1
