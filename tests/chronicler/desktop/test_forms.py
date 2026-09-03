"""Tests for the archive view's form dialogs."""

from unittest.mock import MagicMock

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.forms import (
    CreateChronicleForm,
    EditChronicleForm,
    TranscriptImportForm,
)


@pytest.fixture
def page():
    page = MagicMock(spec=ft.Page)
    page.overlay = []
    return page


@pytest.fixture(params=[CreateChronicleForm, EditChronicleForm, TranscriptImportForm])
def any_form(request):
    return request.param(MagicMock(), MagicMock())


def test_attach_adds_the_dialog_to_the_overlay_once(any_form, page):
    any_form.attach(page)
    any_form.attach(page)

    assert page.overlay == [any_form.dialog]


def test_detach_removes_the_dialog_and_tolerates_being_called_twice(any_form, page):
    any_form.attach(page)

    any_form.detach(page)
    any_form.detach(page)

    assert page.overlay == []


def test_open_and_close_toggle_the_dialog_and_refresh_the_page(any_form, page):
    any_form.open(page)
    assert any_form.dialog.open is True

    any_form.close(page)
    assert any_form.dialog.open is False
    assert page.update.call_count == 2


def test_create_form_reports_and_clears_its_title():
    form = CreateChronicleForm(MagicMock(), MagicMock())
    form.title_field.value = "New Chronicle"

    assert form.title == "New Chronicle"

    form.clear()
    assert form.title == ""


def test_edit_form_fills_from_a_chronicle():
    form = EditChronicleForm(MagicMock(), MagicMock())

    form.fill_from(
        Chronicle(
            title="Original Title",
            description="Original desc",
            kind="Podcast",
            duration="1h",
        )
    )

    assert form.title_field.value == "Original Title"
    assert form.description_field.value == "Original desc"
    assert form.kind_field.value == "Podcast"
    assert form.duration_field.value == "1h"


def test_edit_form_blanks_the_kind_field_when_it_is_the_unknown_default():
    """
    "Unknown" is the model default, not a value the user typed - the field should start
    blank rather than round-tripping the placeholder as if it were real data.
    """
    form = EditChronicleForm(MagicMock(), MagicMock())

    form.fill_from(Chronicle(title="Some Chronicle"))

    assert form.kind_field.value == ""


def test_edit_form_applies_edits_back_onto_the_chronicle():
    form = EditChronicleForm(MagicMock(), MagicMock())
    form.title_field.value = "New Title"
    form.description_field.value = "New description"
    form.kind_field.value = "Meeting"
    form.duration_field.value = "45m"

    updated = form.apply_to(Chronicle(title="Old Title", kind="Unknown"))

    assert updated.title == "New Title"
    assert updated.description == "New description"
    assert updated.kind == "Meeting"
    assert updated.duration == "45m"


def test_edit_form_keeps_the_existing_title_and_restores_defaults_when_blanked():
    form = EditChronicleForm(MagicMock(), MagicMock())
    form.title_field.value = ""
    form.description_field.value = ""
    form.kind_field.value = ""
    form.duration_field.value = ""

    updated = form.apply_to(Chronicle(title="Keep Me", kind="Podcast", duration="1h"))

    assert updated.title == "Keep Me"
    assert updated.description is None
    assert updated.kind == "Unknown"
    assert updated.duration is None


def test_transcript_form_defaults_to_group_1_and_2_with_no_timestamps():
    options = TranscriptImportForm(MagicMock(), MagicMock()).options()

    assert options.speaker_group == 1
    assert options.text_group == 2
    assert options.timestamp_group is None
    assert options.regex


def test_transcript_form_parses_group_indices_as_ints():
    form = TranscriptImportForm(MagicMock(), MagicMock())
    form.regex_field.value = r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$"
    form.speaker_group_field.value = "2"
    form.text_group_field.value = "3"
    form.timestamp_group_field.value = "1"

    options = form.options()

    assert (options.speaker_group, options.text_group, options.timestamp_group) == (2, 3, 1)


def test_transcript_form_treats_a_blank_timestamp_field_as_no_timestamps():
    """
    Blank must mean None, not group 0 - group 0 is the whole match, which would silently
    produce nonsense timestamps.
    """
    form = TranscriptImportForm(MagicMock(), MagicMock())
    form.timestamp_group_field.value = "   "

    assert form.options().timestamp_group is None


def test_transcript_form_falls_back_to_defaults_when_group_fields_are_cleared():
    form = TranscriptImportForm(MagicMock(), MagicMock())
    form.speaker_group_field.value = ""
    form.text_group_field.value = ""

    options = form.options()

    assert (options.speaker_group, options.text_group) == (1, 2)
