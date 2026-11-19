"""The transcript view's Tags section."""

from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest

from chronicler.core.models import Chronicle, Tag
from chronicler.desktop.theme import theme_colors
from chronicler.desktop.views.transcript.tags import TagsPanel
from tests.chronicler.desktop.controls import find_controls, text_values


def _panel(chronicle=None, service=None):
    chronicle = chronicle or Chronicle(title="T")
    service = service or AsyncMock()
    panel = TagsPanel(chronicle, service, theme_colors(True), MagicMock())
    panel.chips.update = MagicMock()
    panel.field.update = MagicMock()
    return panel, chronicle, service


def _event(value=None, data=None):
    return MagicMock(control=MagicMock(value=value, data=data))


def test_a_chronicle_with_no_tags_says_so():
    panel, _, _ = _panel()

    assert text_values(panel) == ["No tags"]


def test_each_tag_is_a_chip():
    panel, _, _ = _panel(Chronicle(title="T", tags=[Tag(name="a"), Tag(name="b")]))

    chips = find_controls(panel, lambda c: isinstance(c, ft.Chip))

    assert [chip.data for chip in chips] == ["a", "b"]


@pytest.mark.asyncio
async def test_submitting_a_name_adds_it_and_clears_the_field():
    panel, chronicle, service = _panel()
    service.add_tag.return_value = chronicle.model_copy(update={"tags": [Tag(name="product")]})
    panel.field.value = "product"

    await panel.add_submitted(_event("product"))

    service.add_tag.assert_awaited_once_with(chronicle.id, "product")
    assert text_values(panel) == ["product"]
    assert chronicle.tags[0].name == "product"
    assert panel.field.value == ""


@pytest.mark.asyncio
async def test_a_blank_name_is_not_sent():
    panel, _, service = _panel()

    await panel.add_submitted(_event("   "))

    service.add_tag.assert_not_awaited()


@pytest.mark.asyncio
async def test_removing_a_chip_removes_the_tag():
    chronicle = Chronicle(title="T", tags=[Tag(name="product")])
    panel, _, service = _panel(chronicle)
    service.remove_tag.return_value = chronicle.model_copy(update={"tags": []})

    await panel.remove_clicked(_event(data="product"))

    service.remove_tag.assert_awaited_once_with(chronicle.id, "product")
    assert text_values(panel) == ["No tags"]


@pytest.mark.asyncio
async def test_a_failure_is_said_and_leaves_the_tags_as_they_were():
    chronicle = Chronicle(title="T", tags=[Tag(name="keep")])
    panel, _, service = _panel(chronicle)
    service.remove_tag.side_effect = RuntimeError("db is gone")

    await panel.remove_clicked(_event(data="keep"))

    panel.show_snackbar.assert_called_once()
    assert "db is gone" in panel.show_snackbar.call_args[0][0]
    assert [tag.name for tag in chronicle.tags] == ["keep"]
