"""Export canonical DESIGN.md tables to a self-contained theme include."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def export(source: str) -> tuple[str, dict[str, list[str]], dict[str, str]]:
    """Read the canonical tables, retaining their theme and family assignments."""
    themes: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    families: dict[str, list[str]] = {}
    section = ""
    for line in source.splitlines():
        if line.startswith("### Light theme"):
            section = "light"
        elif line.startswith("### Dark theme"):
            section = "dark"
        elif line.startswith("### Semantic colors"):
            section = "semantic"
        elif line.startswith("### Categorical palette"):
            section = "palette"
        elif line.startswith("##"):
            section = ""
        colors = re.findall(r"#[0-9a-fA-F]{6}", line)
        token = re.search(r"`--([a-z-]+)`", line)
        if section in themes and token and colors:
            themes[section][token[1]] = colors[0]
        elif section == "semantic" and colors:
            name = line.split("|")[1].strip().lower().replace(" value", "")
            if len(colors) == 4:
                for theme, offset in (("light", 0), ("dark", 2)):
                    themes[theme][name] = colors[offset]
                    themes[theme][f"{name}-bg"] = colors[offset + 1]
            elif len(colors) == 2:
                themes["light"][name], themes["dark"][name] = colors
        elif section == "palette" and len(colors) == 5:
            families[line.split("|")[1].strip().split()[0].lower()] = colors
    if any(len(tokens) != 20 for tokens in themes.values()) or len(families) != 9:
        raise ValueError("Canonical design tables changed. Review the exporter before updating.")
    font = re.search(r"font-family: ([^;]+);", source)
    if font is None:
        raise ValueError("Canonical font stack is missing")

    def declarations(theme: str) -> str:
        return ";".join(f"--{name}:{value}" for name, value in themes[theme].items()) + ";"

    light = themes["light"]
    css = (
        "/* Generated from barbieri-playground/design/DESIGN.md. Do not edit tokens. */\n"
        f":root{{color-scheme:light dark;{declarations('light')}}}\n"
        f"@media(prefers-color-scheme:dark){{:root:not([data-theme=light]){{{declarations('dark')}}}}}\n"
        f":root[data-theme=light]{{color-scheme:light;{declarations('light')}}}\n"
        f":root[data-theme=dark]{{color-scheme:dark;{declarations('dark')}}}\n"
        "body{margin:0;padding:24px;"
        "background:var(--surface-sunken);"
        f"color:var(--text);font:400 15px/1.5 {font[1]};}}\n"
        "main{max-width:760px;margin:auto;padding:24px;background:var(--surface);"
        "color:var(--text);border:1px solid var(--border);border-radius:12px}\n"
        "h1{font-size:24px;font-weight:500}h2{font-size:18px;"
        "font-weight:500}h3{font-size:16px;font-weight:500}\n"
        # Links keep an underline everywhere and declare a literal fallback
        # before the token: clients that do not resolve custom properties then
        # still get the light-theme accent instead of inherited body text.
        f"a{{color:{light['accent']};color:var(--accent);text-decoration:underline}}\n"
        "table{width:100%;border-collapse:collapse;font-size:14px;"
        "font-variant-numeric:tabular-nums}\n"
        "th,td{border:1px solid var(--border-strong);padding:8px;"
        "text-align:left}th{background:var(--accent-soft);font-weight:500}\n"
        # Numeric report cells stay right-aligned (report-html-contract); this
        # bare rule covers unscoped email documents.
        "td.report-table-value{text-align:right}\n"
        "hr{border:0;border-top:1px solid var(--border);margin:22px 0}\n"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;"
        "background:var(--surface-sunken);color:var(--text);padding:16px;border-radius:12px}\n"
        ".material-icon{width:24px;height:24px;vertical-align:middle;"
        "fill:currentColor;margin-right:8px}\n"
    )
    css = css.replace(
        "background:var(--surface-sunken)",
        f"background:{light['surface-sunken']};background:var(--surface-sunken)",
    )
    css = css.replace(
        "background:var(--surface);", f"background:{light['surface']};background:var(--surface);"
    )
    css = css.replace("color:var(--text);", f"color:{light['text']};color:var(--text);")
    return css.replace(";", ";\n").replace("}", "}\n"), families, light


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--format", choices=("python", "typescript", "css", "hbs"), required=True)
    parser.add_argument("--scope", choices=("report",))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the destination is out of date.",
    )
    args = parser.parse_args()
    css, families, light = export(args.source.read_text())
    if args.scope == "report":
        css = re.sub(r"(background|color):#[0-9a-f]{6};\n(?=(?:background|color):var)", "", css)
        css = css.replace(":root", ".gustavo-report")
        css = css.replace(
            ".gustavo-report[data-theme=light]",
            ":root:is(.light,[data-theme=light]) .gustavo-report",
        )
        css = css.replace(
            ".gustavo-report[data-theme=dark]", ":root:is(.dark,[data-theme=dark]) .gustavo-report"
        )
        css = css.replace(
            ".gustavo-report:not([data-theme=light])",
            ":root:not(.light):not([data-theme=light]) .gustavo-report",
        )
        css = css.replace("body{", ".gustavo-report{")
        css = re.sub(
            r"(?m)(?<![\w.-])(main|h1|h2|h3|a|table|th|td|hr|pre)(?=[{:,])",
            r".gustavo-report \1",
            css,
        )
        css = css.replace(".material-icon{", ".gustavo-report .material-icon{")
        # Scoped numeric-cell rule with enough specificity to beat the shared
        # td rule above (same contract as the email's bare rule).
        css += ".gustavo-report td.report-table-value{text-align:right}\n"
        body = re.search(r"\.gustavo-report\{margin.*?}", css, re.S)
        if body is None:
            raise ValueError("Report surface styles are missing")
        css = body[0] + "\n" + css[: body.start()] + css[body.end() :]
        # Low specificity lets host theme hooks override the shared defaults.
        css = css.replace(".gustavo-report{", ":where(.gustavo-report){")
    if args.format == "python":
        result = (
            '"""Generated Gustavo Style include. See design/README.md."""\n\n'
            + 'CSS = """\n'
            + css
            + '"""\n'
        )
    elif args.format == "typescript":
        result = (
            "// Generated Gustavo Style include. See design/README.md.\n"
            + "export const GUSTAVO_STYLE_CSS = "
            + json.dumps(css)
            + ";\n"
            + "export const CHART_FAMILIES = "
            + json.dumps(families)
            + " as const;\n"
            + "export const LIGHT_TOKENS = "
            + json.dumps(light)
            + " as const;\n"
        )
    else:
        result = f"<style>\n{css}</style>\n" if args.format == "hbs" else css
    if args.check:
        current = args.destination.read_text() if args.destination.exists() else None
        if current != result:
            raise SystemExit(
                f"{args.destination} is out of date with the canonical DESIGN.md; "
                "re-run the exporter without --check."
            )
        return
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(result)


if __name__ == "__main__":
    main()
