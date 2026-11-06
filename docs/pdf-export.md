# PDF export

`chronicler/core/services/pdf.py`, `chronicler/core/services/fonts/`

## Fonts

The PDF used to be set in Helvetica, one of the PDF standard fonts, which only covers
Latin-1. Text was squeezed through Latin-1 with `?` as the replacement, and then every
`?` was removed, real question marks included:

```text
input    Are you sure? Ja, natürlich. Łódź 你好
output   Are you sure Ja, natürlich. ód
```

Text is now set in **DejaVu Sans**, bundled in the package with its licence. It covers
Latin, Greek and Cyrillic, which is every alphabet the transcription language list needs
apart from CJK.

CJK fonts run to tens of megabytes, too large to bundle. `format_pdf` looks for one the
operating system already has (Microsoft YaHei and friends on Windows, PingFang and
Hiragino on macOS, Noto CJK or WenQuanYi on Linux) and registers it as a fallback.

Anything neither font can draw is listed at the top of the document as code points
(`U+4F60`), and logged. The note uses code points because it is set in the same font
that lacks those characters.

## Layout

Timestamp, speaker and text are three columns. A long speaker name wraps within its
column instead of being cut at 12 characters, and the row is as tall as whichever column
needs more lines.

## Packaging

The fonts live inside the `chronicler` package, so the wheel and the embedded-runtime
build carry them automatically. The PyInstaller build does not collect data files on its
own, so `Chronicler.spec` and `scripts/pack.sh` list the `fonts/` directory explicitly.
