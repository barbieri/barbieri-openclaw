from __future__ import annotations

import html
import re


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
        if skipping and (line.startswith("**Legend:") or line.startswith("**📊 Legenda:")):
            skipping = False
        if not skipping:
            filtered.append(line)

    return "\n".join(filtered).strip() + "\n"


def markdown_to_html(markdown_text: str) -> str:
    lines = strip_chat_instructions(markdown_text).splitlines()
    body: list[str] = []
    list_open = False
    table: list[str] = []

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
        headers = split_markdown_row(table[0])
        body.append("<thead><tr>")
        for header in headers:
            body.append(f"<th>{inline_markdown_to_html(header)}</th>")
        body.append("</tr></thead><tbody>")
        for row in table[2:]:
            cells = split_markdown_row(row)
            body.append("<tr>")
            for cell in cells:
                body.append(f"<td>{inline_markdown_to_html(cell)}</td>")
            body.append("</tr>")
        body.append("</tbody></table>")
        table = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("|"):
            close_list()
            table.append(stripped)
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
            body.append(f"<h4>{inline_markdown_to_html(stripped[5:])}</h4>")
            continue
        if stripped.startswith("### "):
            close_list()
            body.append(f"<h3>{inline_markdown_to_html(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            close_list()
            body.append(f"<h2>{inline_markdown_to_html(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            close_list()
            body.append(f"<h1>{inline_markdown_to_html(stripped[2:])}</h1>")
            continue
        if stripped.startswith("- "):
            if not list_open:
                body.append("<ul>")
                list_open = True
            body.append(f"<li>{inline_markdown_to_html(stripped[2:])}</li>")
            continue

        close_list()
        body.append(f"<p>{inline_markdown_to_html(stripped)}</p>")

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


def inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"_(.+?)_", r"<em>\1</em>", escaped)


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
