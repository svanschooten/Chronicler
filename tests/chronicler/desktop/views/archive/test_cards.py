"""Tests for the chronicle card builder."""

import inspect
from unittest.mock import AsyncMock

import flet as ft
import pytest

from chronicler.core.models import Chronicle, Tag
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.archive.cards import ChronicleCardHandlers, chronicle_card
from tests.chronicler.desktop.controls import find_controls, text_values


def _handlers(**overrides) -> ChronicleCardHandlers:
    fields = {name: AsyncMock() for name in ChronicleCardHandlers.__dataclass_fields__}
    fields.update(overrides)
    return ChronicleCardHandlers(**fields)


def test_card_shows_the_chronicles_metadata():
    chronicle = Chronicle(
        title="Weekly product sync",
        description="Roadmap and priorities.",
        kind="Work meeting",
        status="Ready to review",
        duration="48m",
        speakers_count=4,
    )

    values = text_values(chronicle_card(chronicle, theme_colors(True), _handlers()))

    assert "Weekly product sync" in values
    assert "Roadmap and priorities." in values
    assert "WORK MEETING" in values
    assert "Ready to review" in values
    assert "48m" in values
    assert "4 speakers" in values


def test_card_joins_tag_names_and_falls_back_when_there_are_none():
    tagged = Chronicle(title="T", tags=[Tag(name="product"), Tag(name="weekly")])
    untagged = Chronicle(title="T")

    assert "product · weekly" in text_values(
        chronicle_card(tagged, theme_colors(True), _handlers())
    )
    assert "No tags" in text_values(chronicle_card(untagged, theme_colors(True), _handlers()))


def test_card_fills_in_placeholders_for_missing_optional_metadata():
    values = text_values(chronicle_card(Chronicle(title="T"), theme_colors(True), _handlers()))

    assert "No description" in values
    assert "Unknown duration" in values


def test_card_opens_the_chronicle_when_the_body_is_clicked():
    chronicle = Chronicle(title="T")
    on_open = AsyncMock()

    card = chronicle_card(chronicle, theme_colors(True), _handlers(on_open=on_open))

    assert card.on_click is on_open
    assert card.data is chronicle


def test_card_actions_bind_async_handlers_directly_and_carry_their_data():
    """
    Regression test: a per-card on_click written as `lambda e: self.async_method(e)` is
    never awaited by Flet (it only checks inspect.iscoroutinefunction on the handler object
    itself, not on what it returns) - the coroutine is silently dropped.
    """
    chronicle = Chronicle(title="Some Chronicle")
    on_edit, on_delete = AsyncMock(), AsyncMock()
    handlers = _handlers(on_edit=on_edit, on_delete=on_delete)

    card = chronicle_card(chronicle, theme_colors(True), handlers)

    actions = [
        c
        for c in find_controls(card, lambda c: isinstance(c, (ft.PopupMenuItem, ft.IconButton)))
        if getattr(c, "on_click", None)
    ]
    assert len(actions) == 6

    for action in actions:
        assert inspect.iscoroutinefunction(action.on_click), (
            f"{action} on_click must be the async handler itself, not a lambda wrapping it"
        )
        assert action.data == chronicle, "every operation takes the whole Chronicle"


@pytest.mark.parametrize("dark_mode", [True, False])
def test_card_takes_its_colors_from_the_palette(dark_mode):
    """
    Regression test: the card used to hardcode BLUE_GREY card colors regardless of the
    dark_mode setting, so light mode left every card looking exactly as dark.
    """
    colors = theme_colors(dark_mode)

    card = chronicle_card(Chronicle(title="T"), colors, _handlers())

    assert card.bgcolor == colors.card


def test_dark_and_light_cards_differ():
    dark = chronicle_card(Chronicle(title="T"), theme_colors(True), _handlers())
    light = chronicle_card(Chronicle(title="T"), theme_colors(False), _handlers())

    assert dark.bgcolor != light.bgcolor
