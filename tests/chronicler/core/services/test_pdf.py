"""Tests for PDF export: what goes in must come out."""

import io
import warnings
from pathlib import Path

import pytest
from pypdf import PdfReader

from chronicler.core.models import TranscriptLine
from chronicler.core.services.pdf import format_pdf

SAMPLE = "Are you sure? Ja, natürlich. Łódź Ελληνικά Привет"
CJK = "你好"
SYSTEM_CJK_FONT = Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")


def _line(text, speaker="Alice", start=0.0):
    return TranscriptLine(speaker_name=speaker, text=text, start_time=start, end_time=start + 1)


def _text_of(pdf: bytearray) -> str:
    reader = PdfReader(io.BytesIO(bytes(pdf)))
    return "\n".join(page.extract_text() for page in reader.pages)


def _squashed(text: str) -> str:
    """Extraction can break lines and spaces differently than they were set."""
    return "".join(text.split())


def test_latin_greek_and_cyrillic_text_survive():
    text = _text_of(format_pdf([_line(SAMPLE)], "Session", fallback_fonts=[]))

    assert _squashed(SAMPLE) in _squashed(text)


def test_the_title_keeps_its_question_mark():
    text = _text_of(format_pdf([_line("Hi")], "Who goes there?", fallback_fonts=[]))

    assert "Who goes there?" in text


def test_without_a_cjk_font_the_document_says_what_is_missing():
    text = _text_of(format_pdf([_line(f"{SAMPLE} {CJK}")], "Session", fallback_fonts=[]))

    assert "could not be rendered" in text
    assert "U+4F60" in text and "U+597D" in text
    assert _squashed(SAMPLE) in _squashed(text)


def test_text_that_fits_has_no_missing_characters_note():
    text = _text_of(format_pdf([_line(SAMPLE)], "Session", fallback_fonts=[]))

    assert "could not be rendered" not in text


@pytest.mark.skipif(not SYSTEM_CJK_FONT.exists(), reason="no CJK font on this machine")
def test_a_system_cjk_font_draws_cjk_text():
    text = _text_of(
        format_pdf([_line(f"{SAMPLE} {CJK}")], "Session", fallback_fonts=[SYSTEM_CJK_FONT])
    )

    assert CJK in _squashed(text)
    assert "could not be rendered" not in text


def test_a_long_speaker_name_is_not_cut_short():
    speaker = "Lady Evangeline of the Northern Marches"

    text = _text_of(format_pdf([_line("We ride.", speaker=speaker)], "S", fallback_fonts=[]))

    assert _squashed(speaker) in _squashed(text)


def test_rendering_raises_no_deprecation_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        format_pdf([_line(SAMPLE)], "Session", fallback_fonts=[])


def test_an_all_latin_export_does_not_load_the_fallback_font(monkeypatch):
    """Loading a 17 MB CJK font made a 300-line Latin export take 1 s instead of 0.2 s."""
    from chronicler.core.services.pdf import TranscriptPDF

    loads = []
    monkeypatch.setattr(TranscriptPDF, "load_fallback", lambda self, c=None: loads.append(c))

    format_pdf([_line(SAMPLE)], "Session", fallback_fonts=[SYSTEM_CJK_FONT])

    assert loads == []


@pytest.mark.skipif(not SYSTEM_CJK_FONT.exists(), reason="no CJK font on this machine")
def test_subsetting_a_system_font_prints_no_warnings(caplog):
    with caplog.at_level("WARNING"):
        format_pdf([_line(CJK)], "Session", fallback_fonts=[SYSTEM_CJK_FONT])

    assert "fontTools" not in caplog.text
