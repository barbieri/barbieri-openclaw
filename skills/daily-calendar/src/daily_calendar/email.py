from __future__ import annotations

import html
import re
from typing import Literal, NamedTuple
from urllib.parse import urlsplit

_MARKDOWN_LINK_START = re.compile(r"(?<!\\)\[((?:\\.|[^\\\]\n]){1,256})]\(")
_ESCAPED_PUNCTUATION = re.compile(r"\\([\[\]*_])")
_MAX_LINK_TARGET_LENGTH = 2048


class ReportSegment(NamedTuple):
    text: str
    source: Literal["calendar", "digest"]


def strip_chat_instructions(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    filtered: list[str] = []
    skipping = False

    for line in lines:
        if line.startswith("**How to use event numbers:") or line.startswith(
            "**💡 Como usar os números"
        ):
            skipping = True
            continue
        if skipping:
            if line.startswith("- "):
                continue
            skipping = False
            if not line.strip():
                continue
        filtered.append(line)

    return "\n".join(filtered).strip() + "\n"


def report_segments(
    calendar_body: str, digest_markdown: str, *, footer: str | None = None
) -> tuple[ReportSegment, ...]:
    digest = digest_markdown.rstrip()
    if not digest:
        if footer is None:
            return (ReportSegment(calendar_body, "calendar"),)
        return (
            ReportSegment(f"{calendar_body}\n", "calendar"),
            ReportSegment(footer, "calendar"),
        )
    if footer is not None:
        return (
            ReportSegment(f"{calendar_body}\n", "calendar"),
            ReportSegment(f"{digest}\n\n", "digest"),
            ReportSegment(footer, "calendar"),
        )
    return (
        ReportSegment(f"{calendar_body}\n", "calendar"),
        ReportSegment(f"{digest}\n", "digest"),
    )


def compose_report_markdown(
    calendar_body: str, digest_markdown: str, *, footer: str | None = None
) -> str:
    return "".join(
        segment.text for segment in report_segments(calendar_body, digest_markdown, footer=footer)
    )


def markdown_to_html(
    calendar_body: str, digest_markdown: str = "", *, footer: str | None = None
) -> str:
    lines = [
        (line, segment.source == "digest")
        for segment in report_segments(
            strip_chat_instructions(calendar_body), digest_markdown, footer=footer
        )
        for line in segment.text.splitlines()
    ]
    body: list[str] = []
    list_open = False
    table: list[tuple[str, bool]] = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            body.append("</ul>")
            list_open = False

    def flush_table() -> None:
        nonlocal table
        if not table:
            return
        body.append('<table role="presentation">')
        headers = split_markdown_row(table[0][0])
        body.append("<thead><tr>")
        for header in headers:
            body.append(f"<th>{inline_markdown_to_html(header, links=table[0][1])}</th>")
        body.append("</tr></thead><tbody>")
        for row, links in table[2:]:
            cells = split_markdown_row(row)
            body.append("<tr>")
            for cell in cells:
                body.append(f"<td>{inline_markdown_to_html(cell, links=links)}</td>")
            body.append("</tr>")
        body.append("</tbody></table>")
        table = []

    for line, links in lines:
        stripped = line.strip()

        if stripped.startswith("|"):
            close_list()
            table.append((stripped, links))
            continue

        flush_table()

        if not stripped:
            close_list()
            continue
        if stripped == "---":
            close_list()
            body.append("<hr>")
            continue
        if stripped.startswith("#### "):
            close_list()
            body.append(f"<h4>{inline_markdown_to_html(stripped[5:], links=links)}</h4>")
            continue
        if stripped.startswith("### "):
            close_list()
            body.append(f"<h3>{inline_markdown_to_html(stripped[4:], links=links)}</h3>")
            continue
        if stripped.startswith("## "):
            close_list()
            body.append(f"<h2>{inline_markdown_to_html(stripped[3:], links=links)}</h2>")
            continue
        if stripped.startswith("# "):
            close_list()
            body.append(f"<h1>{inline_markdown_to_html(stripped[2:], links=links)}</h1>")
            continue
        if stripped.startswith("- "):
            if not list_open:
                body.append("<ul>")
                list_open = True
            body.append(f"<li>{inline_markdown_to_html(stripped[2:], links=links)}</li>")
            continue

        close_list()
        body.append(f"<p>{inline_markdown_to_html(stripped, links=links)}</p>")

    flush_table()
    close_list()

    rendered_body = "\n".join(f"    {line}" for line in body)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #f6f7f9;
      color: #1f2937;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    main {{
      max-width: 760px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 24px;
    }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    h2 {{ margin: 28px 0 12px; font-size: 18px; }}
    h3 {{ margin: 22px 0 10px; font-size: 16px; }}
    h4 {{ margin: 18px 0 8px; font-size: 15px; }}
    p {{ margin: 8px 0 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 8px 0 16px; font-size: 14px; }}
    th, td {{
      border: 1px solid #d8dee8;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #eef2f7; font-weight: 700; }}
    hr {{ border: 0; border-top: 1px solid #e5e7eb; margin: 22px 0; }}
    ul {{ margin: 8px 0 14px 22px; padding: 0; }}
  </style>
</head>
<body>
  <main>
{rendered_body}
  </main>
</body>
</html>
"""


def inline_markdown_to_html(text: str, *, links: bool = False) -> str:
    if not links:
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        return re.sub(r"_(.+?)_", r"<em>\1</em>", escaped)

    parts: list[str] = []
    position = 0
    for match in _MARKDOWN_LINK_START.finditer(text):
        if match.start() < position:
            continue
        if not text.startswith(("http://", "https://"), match.end()):
            continue
        target = _link_target(text, match.end())
        if target is None:
            continue
        url, end = target
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or any(char in url for char in "<>")
        ):
            continue
        parts.append(_format_inline_text(text[position : match.start()]))
        parts.append(
            f'<a href="{html.escape(url, quote=True)}">{_format_inline_text(match[1])}</a>'
        )
        position = end
    parts.append(_format_inline_text(text[position:]))
    return "".join(parts)


def _link_target(text: str, start: int) -> tuple[str, int] | None:
    if text.find(")", start, start + _MAX_LINK_TARGET_LENGTH) < 0:
        return None
    depth = 1
    target: list[str] = []
    index = start
    while index < len(text) and index - start < _MAX_LINK_TARGET_LENGTH:
        char = text[index]
        if char.isspace():
            return None
        if char == "\\" and index + 1 < len(text) and text[index + 1] in "()\\":
            target.append(text[index + 1])
            index += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return "".join(target), index + 1
        target.append(char)
        index += 1
    return None


def _format_inline_text(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"(?<!\\)\*\*(.+?)(?<!\\)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\\)_(.+?)(?<!\\)_", r"<em>\1</em>", escaped)
    return _ESCAPED_PUNCTUATION.sub(r"\1", escaped)


def markdown_to_plain(
    calendar_body: str, digest_markdown: str = "", *, footer: str | None = None
) -> str:
    rendered = "".join(
        _ESCAPED_PUNCTUATION.sub(r"\1", segment.text)
        if segment.source == "digest"
        else segment.text
        for segment in report_segments(
            strip_chat_instructions(calendar_body), digest_markdown, footer=footer
        )
    )
    return rendered if rendered.endswith("\n") else f"{rendered}\n"


def split_markdown_row(row: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    content = row.strip().removeprefix("|").removesuffix("|")
    index = 0

    while index < len(content):
        character = content[index]
        if character == "\\" and index + 1 < len(content) and content[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1

    cells.append("".join(current).strip())
    return cells
