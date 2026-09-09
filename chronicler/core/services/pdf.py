"""PDF (.pdf) rendering for a transcript."""

import datetime
from chronicler.core.models import TranscriptLine
from chronicler.core.formatting import format_timestamp
from fpdf import FPDF


def format_pdf(
    lines: list[TranscriptLine],
    title: str,
) -> bytearray:
    pdf = TranscriptPDF(title=clean_for_pdf(title))
    pdf.add_page()

    for line in lines:
        text = line.text.strip()
        if not text:
            continue

        ts = getattr(line, 'timestamp', None) or getattr(line, 'start_time', None)
        timestamp_str = format_timestamp(ts)

        speaker = line.speaker_name or 'Unknown'
        clean_text = text.replace('\r', '').replace('\n', ' ')

        pdf.add_line(
            timestamp=timestamp_str,
            speaker=speaker,
            text=clean_text,
        )

    return pdf.output()


def clean_for_pdf(text: str) -> str:
    """Remove Unicode chars that Helvetica doesn't support (Latin-1 only)."""
    # Replace CJK, emoji, and other Unicode with '?', keep basic Latin-1
    return text.encode('latin-1', 'replace').decode('latin-1').replace('?', '')


class TranscriptPDF(FPDF):
    """Simple PDF using only built-in Helvetica font."""

    def __init__(self, title: str = "Transcript"):
        super().__init__(unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(left=20, top=20, right=20)
        self.doc_title = title

        # Simple layout widths
        self.ts_width = 20  # timestamp
        self.speaker_width = 25
        self.text_width = 125  # remainder of A4 width

    def header(self):
        """Simple header."""
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 10, self.doc_title, ln=True, align="C")
        self.line(20, 18, 190, 18)
        self.ln(5)

    def footer(self):
        """Page number at bottom."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def add_line(self, timestamp: str, speaker: str, text: str):
        """Add one transcript line."""
        start_y = self.get_y()

        # Page break if needed
        if start_y > 270:
            self.add_page()
            start_y = self.get_y()

        # Timestamp (small, gray)
        self.set_xy(20, start_y)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(100)
        self.cell(self.ts_width, 5, timestamp, ln=0)

        # Speaker (bold)
        self.set_xy(40, start_y)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0)
        speaker_clean = clean_for_pdf(speaker[:12])
        self.cell(self.speaker_width, 5, speaker_clean, ln=0)

        # Text (normal, wrapped)
        self.set_xy(65, start_y)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(50)

        text_clean = clean_for_pdf(text.replace('\n', ' '))
        self.multi_cell(self.text_width, 5, text_clean, ln=1)

        # Small gap between entries
        self.ln(2)
