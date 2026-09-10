"""HTML (.html) rendering for a transcript."""

import datetime
import html

from chronicler.core.formatting import format_timestamp
from chronicler.core.models import TranscriptLine


def format_html(
    lines: list[TranscriptLine],
    title: str,
) -> str:
    entries: list[str] = []
    for line in lines:
        text = line.text.strip()
        if not text:
            continue

        safe_text = html.escape(text).replace('\n', '<br>')
        speaker = line.speaker_name or 'Unknown'
        safe_speaker = html.escape(speaker)

        speaker_class = ' gm' if speaker.strip().upper() == 'GM' else ''
        ts = getattr(line, 'timestamp', None) or getattr(line, 'start_time', None)
        timestamp_str = format_timestamp(float(str(ts)))

        entry = (
            f'        <div class="entry">\n'
            f'            <span class="timestamp">[{timestamp_str}]</span>\n'
            f'            <span class="speaker{speaker_class}">{safe_speaker}</span>\n'
            f'            <span class="dialogue">{safe_text}</span>\n'
            f'        </div>'
        )
        entries.append(entry)

    return HTML_TEMPLATE.format(
        title=html.escape(title),
        date=datetime.datetime.now().strftime("%Y-%m-%d"),
        entries="\n".join(entries)
    )

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.5;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: #2c3e50;
            color: #ecf0f1;
            padding: 20px 30px;
            border-bottom: 3px solid #34495e;
        }}
        .header h1 {{ font-size: 1.5em; font-weight: 600; margin-bottom: 5px; }}
        .header .meta {{ font-size: 0.85em; opacity: 0.8; font-family: monospace; }}
        .transcript {{
            padding: 20px 30px;
            max-height: calc(100vh - 140px);
            overflow-y: auto;
        }}
        .entry {{
            display: flex;
            align-items: flex-start;
            margin-bottom: 8px;
            padding: 4px 0;
            border-bottom: 1px solid #f0f0f0;
        }}
        .entry:last-child {{ border-bottom: none; }}
        .entry:hover {{ background: #fafafa; }}
        .timestamp {{
            font-family: "SF Mono", Monaco, monospace;
            font-size: 0.75em;
            color: #7f8c8d;
            min-width: 70px;
            padding-top: 2px;
            flex-shrink: 0;
        }}
        .speaker {{
            font-weight: 600;
            color: #2c3e50;
            min-width: 80px;
            margin-right: 10px;
            flex-shrink: 0;
            font-size: 0.95em;
        }}
        .speaker.gm {{ color: #8e44ad; }}
        .dialogue {{
            flex: 1;
            color: #444;
            font-size: 0.95em;
            word-wrap: break-word;
        }}
        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .transcript {{ padding: 15px; }}
            .entry {{ flex-direction: column; margin-bottom: 12px; }}
            .timestamp {{ font-size: 0.7em; margin-bottom: 2px; }}
        }}
        @media (prefers-color-scheme: dark) {{
            body {{ background: #1a1a1a; color: #e0e0e0; }}
            .container {{ background: #2d2d2d; }}
            .header {{ background: #1e2a33; }}
            .entry {{ border-bottom-color: #3a3a3a; }}
            .entry:hover {{ background: #363636; }}
            .dialogue {{ color: #ccc; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{title}</h1>
        <div class="meta"> • Exported {date}</div>
    </div>
    <div class="transcript">
{entries}
    </div>
</div>
</body>
</html>"""
