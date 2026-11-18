"""Editing a transcript line through the rendered editor."""

import flet as ft
import pytest

from chronicler.i18n import t
from tests.ui.conftest import CHRONICLE_TITLE, LONG_LINE
from tests.ui.test_views import tap_once

pytestmark = pytest.mark.asyncio

EDITED = "An edited line."
OUTSIDE_THE_LINES = ft.Offset(600, 600)
"""An empty spot below the seeded transcript, inside its panel."""


async def edit_the_long_line(tester) -> None:
    await tap_once(tester, await tester.find_by_text(CHRONICLE_TITLE))
    await tap_once(tester, await tester.find_by_tooltip(t("transcript.edit")))
    # Closed, the line is one rich text with its speaker; open, its text is a field alone.
    assert (await tester.find_by_text(LONG_LINE)).count == 0

    await tap_once(tester, await tester.find_by_text_containing(LONG_LINE))
    field = await tester.find_by_text(LONG_LINE)
    assert field.count == 1
    await tester.enter_text(field, EDITED)


async def test_clicking_away_from_an_edited_line_saves_it(tester):
    await edit_the_long_line(tester)

    await tester.tap_at(OUTSIDE_THE_LINES)
    await tester.pump_and_settle()

    assert (await tester.find_by_text(EDITED)).count == 0
    assert (await tester.find_by_text_containing(EDITED)).count == 1
    assert (await tester.find_by_text_containing(LONG_LINE)).count == 0


@pytest.mark.xfail(
    strict=True,
    reason="Clicking Finish blurs the field first. The blur starts the save, so the "
    "finish finds nothing open and reloads the read view before the save lands.",
)
async def test_finishing_right_after_typing_shows_the_edit(tester):
    await edit_the_long_line(tester)

    await tap_once(tester, await tester.find_by_tooltip(t("transcript.done")))

    assert (await tester.find_by_text_containing(EDITED)).count == 1
