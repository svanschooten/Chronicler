# 017-M1_pdf_text_loss

## PDF export removes every question mark and all non-Latin-1 text

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: exported documents silently differ from the transcript. Change risk: low. |
| reach | All PDF exports. Text in Polish, Japanese or Chinese, which the app offers for transcription, is lost |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/services/pdf.py`, `pyproject.toml`, packaged assets |

### description

`clean_for_pdf` (`pdf.py:39`) encodes to Latin-1 with `replace`, then deletes every `?`,
including real ones.

```text
input    Are you sure? Ja, natürlich. Łódź 你好
output   Are you sure Ja, natürlich. ód
```

Speaker names are also cut at 12 characters (`pdf.py:89`). `ln=True` (`pdf.py:59`) is the
one deprecation warning in the test run, and `FPDF2>=1.7.2` in `pyproject.toml` is far
below what the code needs.

### proposed fix

1. Today: remove `.replace("?", "")`.
2. Embed a Unicode font such as DejaVu Sans with `add_font`, and include it in the wheel
   and both builds. This covers Latin, Greek and Cyrillic.
3. CJK fonts are too large to bundle, so use a system font when one is found. Otherwise
   say in the export that some characters could not be rendered.
4. Let long speaker names wrap, replace `ln=True` with `new_x` and `new_y`, and raise the
   `fpdf2` lower bound.

Done when the sample above round-trips apart from the CJK fallback.

### related tickets

- none
