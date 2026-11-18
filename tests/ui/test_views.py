"""Every view renders, with the seeded data on screen."""

import pytest

from chronicler.i18n import t
from tests.ui.conftest import CHRONICLE_TITLE, SHORT_LINE

pytestmark = pytest.mark.asyncio


async def tap_once(tester, finder) -> None:
    assert finder.count == 1
    await tester.tap(finder)
    await tester.pump_and_settle()


async def test_the_archive_lists_the_seeded_chronicle(tester):
    assert (await tester.find_by_text(t("archive.title"))).count >= 1
    assert (await tester.find_by_text(CHRONICLE_TITLE)).count == 1
    assert (await tester.find_by_text_containing(SHORT_LINE)).count == 0


async def test_opening_a_chronicle_shows_its_transcript(tester):
    await tap_once(tester, await tester.find_by_text(CHRONICLE_TITLE))

    assert (await tester.find_by_text(t("transcript.title"))).count >= 1
    assert (await tester.find_by_text_containing(SHORT_LINE)).count == 1


async def test_the_tasks_and_settings_views_render(tester):
    await tap_once(tester, await tester.find_by_text(t("nav.tasks")))
    assert (await tester.find_by_text(t("tasks.heading"))).count == 1
    assert (await tester.find_by_text(t("tasks.empty"))).count == 1

    await tap_once(tester, await tester.find_by_text(t("nav.settings")))
    assert (await tester.find_by_text(t("settings.subtitle"))).count == 1
    assert (await tester.find_by_text(t("settings.appearance.title"))).count == 1

    await tap_once(tester, await tester.find_by_text(t("nav.archive")))
    assert (await tester.find_by_text(CHRONICLE_TITLE)).count == 1
