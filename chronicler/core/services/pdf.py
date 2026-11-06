"""
PDF (.pdf) rendering for a transcript.

Text is set in the bundled DejaVu Sans, which covers Latin, Greek and Cyrillic. A system
CJK font is used as a fallback when one is installed; CJK fonts are too large to bundle.
Anything neither font can draw is listed in a note at the top of the document rather than
silently dropped. See docs/pdf-export.md.
"""

import logging
import os
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import TTFFont

from chronicler.core.formatting import format_timestamp
from chronicler.core.models import TranscriptLine

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).parent / "fonts"
FAMILY = "DejaVu"
FALLBACK_FAMILY = "Fallback"


def _cjk_font_candidates() -> list[Path]:
    """Fonts with CJK coverage that commonly ship with an operating system."""
    windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    return [
        windows / "msyh.ttc",
        windows / "msgothic.ttc",
        windows / "malgun.ttf",
        windows / "simsun.ttc",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    ]


def format_pdf(
    lines: list[TranscriptLine],
    title: str,
    fallback_fonts: list[Path] | None = None,
) -> bytearray:
    """`fallback_fonts` defaults to the system CJK fonts; tests pass their own."""
    pdf = TranscriptPDF(title=title, fallback_fonts=fallback_fonts)

    rows = []
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        ts = getattr(line, "timestamp", None) or getattr(line, "start_time", None)
        rows.append(
            (
                format_timestamp(float(str(ts))),
                line.speaker_name or "Unknown",
                text.replace("\r", "").replace("\n", " "),
            )
        )

    missing = pdf.unrenderable(title, *(f"{speaker}{text}" for _, speaker, text in rows))
    pdf.add_page()
    if missing:
        logger.warning(f"PDF export of '{title}' cannot draw: {''.join(missing)}")
        # Code points, not the characters: the note is set in a font that lacks them too.
        pdf.add_note(
            "Some characters could not be rendered, because no installed font has them: "
            + ", ".join(f"U+{ord(character):04X}" for character in missing)
        )

    for timestamp, speaker, text in rows:
        pdf.add_line(timestamp=timestamp, speaker=speaker, text=text)

    return pdf.output()


class TranscriptPDF(FPDF):
    """An A4 transcript: timestamp, speaker and text columns."""

    def __init__(self, title: str = "Transcript", fallback_fonts: list[Path] | None = None):
        super().__init__(unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(left=20, top=20, right=20)
        self.doc_title = title

        self.add_font(FAMILY, "", FONT_DIR / "DejaVuSans.ttf")
        self.add_font(FAMILY, "B", FONT_DIR / "DejaVuSans-Bold.ttf")
        self._fallback_loaded = self._load_fallback(
            fallback_fonts if fallback_fonts is not None else _cjk_font_candidates()
        )
        if self._fallback_loaded:
            self.set_fallback_fonts([FALLBACK_FAMILY], exact_match=False)

        self.ts_width = 20
        self.speaker_width = 25
        self.text_width = 125

    def _load_fallback(self, candidates: list[Path]) -> bool:
        for path in candidates:
            if not path.is_file():
                continue
            try:
                self.add_font(FALLBACK_FAMILY, "", path)
            except Exception:
                logger.debug(f"Could not load {path} as a fallback font", exc_info=True)
                continue
            logger.debug(f"PDF fallback font: {path}")
            return True
        return False

    def unrenderable(self, *texts: str) -> list[str]:
        """The distinct characters in `texts` that no loaded font can draw."""
        families = [FAMILY] + ([FALLBACK_FAMILY] if self._fallback_loaded else [])
        covered = [self._cmap(family) for family in families]
        missing: dict[str, None] = {}
        for text in texts:
            for character in text:
                if character.isspace() or not character.isprintable():
                    continue
                if not any(ord(character) in cmap for cmap in covered):
                    missing[character] = None
        return list(missing)

    def _cmap(self, family: str) -> dict[int, str]:
        font = self.fonts[family.lower()]
        assert isinstance(font, TTFFont), "only embedded fonts are registered"
        return font.cmap

    def header(self):
        self.set_font(FAMILY, "B", 12)
        self.cell(0, 10, self.doc_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.line(20, 18, 190, 18)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font(FAMILY, "", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def add_note(self, text: str) -> None:
        self.set_font(FAMILY, "", 8)
        self.set_text_color(150, 0, 0)
        self.multi_cell(0, 4, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def add_line(self, timestamp: str, speaker: str, text: str):
        """One transcript line. A long speaker name wraps within its column."""
        self.set_font(FAMILY, "B", 10)
        wrapped = self.multi_cell(self.speaker_width, 5, speaker, dry_run=True, output="LINES")
        assert isinstance(wrapped, list)
        speaker_rows = len(wrapped)
        if self.get_y() > 270 or self.get_y() + 5 * speaker_rows > self.page_break_trigger:
            self.add_page()
        start_y = self.get_y()
        start_page = self.page

        self.set_xy(20, start_y)
        self.set_font(FAMILY, "", 8)
        self.set_text_color(100)
        self.cell(self.ts_width, 5, timestamp)

        self.set_xy(40, start_y)
        self.set_font(FAMILY, "B", 10)
        self.set_text_color(0)
        self.multi_cell(self.speaker_width, 5, speaker, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        speaker_end = self.get_y()

        self.set_xy(65, start_y)
        self.set_font(FAMILY, "", 10)
        self.set_text_color(50)
        self.multi_cell(self.text_width, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if self.page == start_page:
            self.set_y(max(self.get_y(), speaker_end))
        self.ln(2)
