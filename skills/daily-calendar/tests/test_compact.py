from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from daily_calendar import cli
from daily_calendar.report import CalendarSource, build_calendar_report, build_report_markdown


@pytest.mark.parametrize("include_chat_instructions", [False, True])
def test_compact_report_preserves_calendar_and_appends_before_footer(
    tmp_path: Path, include_chat_instructions: bool
) -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events = {
        "fixture": {
            "events": [
                {
                    "id": f"fake-{day}",
                    "summary": f"Planning {day}",
                    "start": {"dateTime": f"2026-08-{day}T09:00:00+00:00"},
                }
                for day in [18, 19, 21]
            ]
        }
    }
    calendar_report = build_calendar_report(
        events,
        [CalendarSource(account="fixture", label="Fixture")],
        now=now,
        timezone=timezone,
        holidays={"2026-08-21": "Example holiday"},
        compact=True,
        include_chat_instructions=include_chat_instructions,
    )
    report = cli.compose_report_markdown(
        calendar_report.body,
        "## Email summary\n\nCafé update.  \n\n",
        footer=calendar_report.footer,
    )

    for day in [18, 19]:
        assert f"## {datetime(2026, 8, day).strftime('%d/%m (%A)')}" in report
        assert f"| 09:00 | Planning {day} | Fixture |  |" in report
    assert "## Holiday Events" in report
    assert "### 21/08/2026 - **Example holiday**" in report
    assert "| 1 | 09:00 | Planning 21 | Fixture |  |" in report
    assert "---" not in report.splitlines()
    assert "**Legend:**" not in report
    assert "_Declined, free, and birthday events are omitted automatically._" in report
    assert ("**How to use event numbers:**" in report) == include_chat_instructions
    assert report.count("## Email summary") == 1
    assert report.endswith("Café update.\n\n_Generated at: 18/08/2026 08:00_")

    markdown_path = tmp_path / "report.md"
    text_path = tmp_path / "report.email.txt"
    html_path = tmp_path / "report.html"
    cli.write_report_files(
        calendar_report=calendar_report,
        digest_markdown="## Email summary\n\nCafé update.  \n\n",
        markdown_path=markdown_path,
        text_path=text_path,
        html_path=html_path,
    )
    assert markdown_path.read_text(encoding="utf-8") == report
    text = text_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    for content in [text, html]:
        assert "Café update." in content
        assert "Generated at: 18/08/2026 08:00" in content
        assert "How to use event numbers" not in content
        assert "Cancel event #1" not in content
        assert "Declined, free, and birthday events are omitted automatically." in content
    assert text.endswith("_Generated at: 18/08/2026 08:00_\n")
    assert "<h2>Email summary</h2>" in html
    assert "<hr>" not in html


def test_default_report_is_unchanged() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    expected = "\n".join(
        [
            "# Daily Calendar Report",
            "",
            "_Generated at: 18/08/2026 08:00_",
            "",
            "---",
            "",
            f"## {now.strftime('%d/%m (%A)')}",
            "",
            "No events scheduled for this day.",
            "",
            "---",
            "",
            f"## {datetime(2026, 8, 19).strftime('%d/%m (%A)')}",
            "",
            "No events scheduled for this day.",
            "",
            "---",
            "",
            "## Holiday Events",
            "",
            "No events scheduled on configured holidays.",
            "",
            "---",
            "",
            "**Legend:**",
            "- ⚠️ = Overlapping events / Conflict",
            "- 🥵 = Back-to-back / tight transition <5m",
            "- ❓ = Tentative / Maybe",
            "- ⏳ = Needs response",
            "- 🔁 = Recurring event",
            "- 💻 = Online meeting",
            "- 📍 = In-person / physical address",
            "- 👥 = More than 3 invitees",
            "",
            "_Declined, free, and birthday events are omitted automatically._",
            "",
        ]
    )
    assert build_report_markdown({}, [], now=now, timezone=timezone) == expected
    assert cli.compose_report_markdown(expected, "Extra text. \n") == expected + "\nExtra text.\n"


def test_appended_digest_links_render_in_html_email(tmp_path: Path) -> None:
    now = datetime(2026, 8, 18, 8, tzinfo=ZoneInfo("UTC"))
    calendar_report = build_calendar_report(
        {},
        [],
        now=now,
        timezone=ZoneInfo("UTC"),
        compact=True,
    )
    html_path = tmp_path / "report.html"
    cli.write_report_files(
        calendar_report=calendar_report,
        digest_markdown=(
            "## Bloomberg\n"
            "- [US bond yields](https://example.invalid/story?a=1&b=2): yields rose.\n"
            "- [Parentheses](https://example.invalid/story_(update)): details.\n"
            "- [Escaped](https://example.invalid/story\\)update): details.\n"
            "- [Apostrophe](https://example.invalid/john's-story): details.\n"
            "- [Unsafe](javascript:alert(1)): ignore this link.\n"
        ),
        markdown_path=tmp_path / "report.md",
        text_path=tmp_path / "report.email.txt",
        html_path=html_path,
    )
    rendered = html_path.read_text(encoding="utf-8")
    assert '<a href="https://example.invalid/story?a=1&amp;b=2">US bond yields</a>' in rendered
    assert '<a href="https://example.invalid/story_(update)">Parentheses</a>: details.' in rendered
    assert '<a href="https://example.invalid/story)update">Escaped</a>: details.' in rendered
    assert '<a href="https://example.invalid/john&#x27;s-story">Apostrophe</a>' in rendered
    assert "[US bond yields](" not in rendered
    assert 'href="javascript:' not in rendered


def test_calendar_event_link_stays_plain_text_while_digest_link_renders() -> None:
    timezone = ZoneInfo("UTC")
    calendar_report = build_calendar_report(
        {
            "fixture": {
                "events": [
                    {
                        "id": "fake-event",
                        "summary": "[Payroll](https://example.invalid/login)",
                        "start": {"dateTime": "2026-08-18T09:00:00+00:00"},
                    }
                ]
            }
        },
        [CalendarSource(account="fixture", label="Fixture")],
        now=datetime(2026, 8, 18, 8, tzinfo=timezone),
        timezone=timezone,
        compact=True,
    )
    rendered = cli.markdown_to_html(
        calendar_report.body,
        "[Article](https://example.invalid/story)",
        footer=calendar_report.footer,
    )

    assert "[Payroll](https://example.invalid/login)" in rendered
    assert 'href="https://example.invalid/login"' not in rendered
    assert '<a href="https://example.invalid/story">Article</a>' in rendered


def test_calendar_literals_stay_literal_and_digest_instructions_are_preserved() -> None:
    timezone = ZoneInfo("UTC")
    calendar_report = build_report_markdown(
        {
            "fixture": {
                "events": [
                    {
                        "id": "fake-event",
                        "summary": r"C:\[archive] [Standup]",
                        "start": {"dateTime": "2026-08-18T09:00:00+00:00"},
                    },
                    {
                        "id": "fake-link",
                        "summary": "[Payroll](https://example.invalid/login)",
                        "start": {"dateTime": "2026-08-18T10:00:00+00:00"},
                    },
                ]
            }
        },
        [CalendarSource(account="fixture", label="Fixture")],
        now=datetime(2026, 8, 18, 8, tzinfo=timezone),
        timezone=timezone,
        include_chat_instructions=True,
    )
    digest = "**How to use event numbers:**\nKeep this digest heading."
    markdown = cli.compose_report_markdown(calendar_report, digest)
    rendered = cli.markdown_to_html(calendar_report, digest)
    plain = cli.markdown_to_plain(calendar_report, digest)

    for output in [markdown, plain, rendered]:
        assert r"C:\[archive] [Standup]" in output
        assert "[Payroll](https://example.invalid/login)" in output
    assert 'href="https://example.invalid/login"' not in rendered
    assert "**How to use event numbers:**\nKeep this digest heading." in plain
    assert "<strong>How to use event numbers:</strong>" in rendered
    assert "Cancel event #1" not in plain
    assert "Cancel event #1" not in rendered


def test_malformed_digest_links_have_bounded_parsing() -> None:
    malformed = "[x](" * 5000
    rendered = cli.markdown_to_html("# Calendar", malformed)
    assert "<a href=" not in rendered
    assert malformed in rendered


def test_untrusted_digest_text_is_escaped_once_in_html_and_readable_in_plain_text() -> None:
    markdown = r"[R&D \[Q4\]](https://example.invalid/story): A & B with \_underscores\_."
    rendered = cli.markdown_to_html("# Calendar", markdown)
    plain = cli.markdown_to_plain("# Calendar", markdown)

    assert '<a href="https://example.invalid/story">R&amp;D [Q4]</a>' in rendered
    assert "A &amp; B with _underscores_." in rendered
    assert "&amp;amp;" not in rendered
    expected_plain = "# Calendar\n\n[R&D [Q4]](https://example.invalid/story): "
    expected_plain += "A & B with _underscores_.\n"
    assert plain == expected_plain


def test_digest_unc_path_keeps_literal_backslashes_in_email() -> None:
    digest = r"Share: \\server\share\Q4 and \[status\]"

    plain = cli.markdown_to_plain("# Calendar", digest)
    rendered = cli.markdown_to_html("# Calendar", digest)

    assert r"\\server\share\Q4 and [status]" in plain
    assert r"\\server\share\Q4 and [status]" in rendered


def test_chat_instruction_removal_keeps_following_calendar_content() -> None:
    calendar = (
        "# Calendar\n\n"
        "**How to use event numbers:**\n"
        '- Cancel: "Cancel event #1"\n'
        '- Reschedule: "Reschedule event #2"\n\n'
        "_Omission note with revised wording._\n\n"
        "**Legend:**\n- Calendar status\n"
    )

    plain = cli.markdown_to_plain(calendar)

    assert "How to use event numbers" not in plain
    assert "Cancel event #1" not in plain
    assert "_Omission note with revised wording._" in plain
    assert "**Legend:**\n- Calendar status" in plain


@pytest.mark.parametrize("compact", [False, True])
def test_cli_composes_once_and_sends_with_explicit_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, compact: bool
) -> None:
    monkeypatch.delenv("DAILY_CALENDAR_ACCOUNTS", raising=False)
    monkeypatch.delenv("DAILY_CALENDAR_HOLIDAYS_FILE", raising=False)
    append_path = tmp_path / "email.md"
    append_path.write_text("## Email summary\n\n---\n\nRésumé.  \n", encoding="utf-8")
    monkeypatch.setattr(cli, "fetch_calendar_events", Mock(return_value={"events": []}))
    writer = Mock(wraps=cli.write_report_files)
    monkeypatch.setattr(cli, "write_report_files", writer)
    commands = Mock()
    monkeypatch.setattr(cli.subprocess, "run", commands)
    args = [
        "--calendar-account",
        "fixture=Fixture",
        "--timezone",
        "UTC",
        "--output-dir",
        str(tmp_path),
        "--append-markdown-file",
        str(append_path),
        "--send-email",
        "--gmail-account",
        "fake-sender",
        "--to",
        "fake-recipient",
        "--gog-bin",
        "fake-gog",
        "--include-chat-instructions",
    ]
    if compact:
        args.append("--compact")
    assert cli.main(args) == 0
    writer.assert_called_once()
    commands.assert_called_once()
    command = commands.call_args.args[0]
    assert command[:7] == [
        "fake-gog",
        "gmail",
        "send",
        "-a",
        "fake-sender",
        "--to",
        "fake-recipient",
    ]
    text = Path(command[command.index("--body-file") + 1]).read_text(encoding="utf-8")
    html = Path(command[command.index("--body-html-file") + 1]).read_text(encoding="utf-8")
    assert text.count("## Email summary") == 1
    assert "## Email summary\n\n---\n\nRésumé." in text
    assert "Résumé." in text
    assert "Résumé." in html
    assert "How to use event numbers" not in text
    if compact:
        assert text.splitlines()[-1].startswith("_Generated at:")
    else:
        assert text.endswith("Résumé.\n")


@pytest.mark.parametrize("file_kind", ["missing", "directory", "invalid-utf8", "unreadable"])
def test_bad_append_file_fails_before_fetch_write_or_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, file_kind: str
) -> None:
    append_path = tmp_path / "append.md"
    if file_kind == "directory":
        append_path.mkdir()
    elif file_kind == "invalid-utf8":
        append_path.write_bytes(b"\xff")
    elif file_kind == "unreadable":
        monkeypatch.setattr(Path, "read_text", Mock(side_effect=PermissionError("unreadable file")))
    fetch = Mock()
    writer = Mock()
    sender = Mock()
    monkeypatch.setattr(cli, "fetch_calendar_events", fetch)
    monkeypatch.setattr(cli, "write_report_files", writer)
    monkeypatch.setattr(cli, "send_email", sender)
    assert (
        cli.main(
            [
                "--calendar-account",
                "fixture=Fixture",
                "--timezone",
                "UTC",
                "--append-markdown-file",
                str(append_path),
                "--send-email",
                "--gmail-account",
                "fake-sender",
                "--to",
                "fake-recipient",
            ]
        )
        == 1
    )
    fetch.assert_not_called()
    writer.assert_not_called()
    sender.assert_not_called()
    assert "daily-calendar:" in capsys.readouterr().err


def test_compact_empty_days_and_append_decorations(tmp_path: Path) -> None:
    timezone = ZoneInfo("UTC")
    options = dict(now=datetime(2026, 8, 18, tzinfo=timezone), timezone=timezone, compact=True)
    calendar_report = build_calendar_report({}, [], **options)
    report = build_report_markdown({}, [], **options)
    assert report.count("No events scheduled for this day.") == 2
    assert "---" not in report.splitlines()
    assert report.endswith("_Generated at: 18/08/2026 00:00_")
    assert (
        cli.compose_report_markdown(calendar_report.body, " \n\t", footer=calendar_report.footer)
        == report
    )
    append_markdown = "---\n**Legend:**\nUser --- text.  \n  ---  \n***\n_ _ _\nFinal text"
    appended = cli.compose_report_markdown(
        calendar_report.body, append_markdown, footer=calendar_report.footer
    )
    assert (
        "**Legend:**\nUser --- text.  \n  ---  \n***\n_ _ _\nFinal text\n\n_Generated at:"
        in appended
    )
    assert [line.strip() for line in appended.splitlines()].count("---") == 2
    markdown_path = tmp_path / "report.md"
    text_path = tmp_path / "report.email.txt"
    html_path = tmp_path / "report.html"
    cli.write_report_files(
        calendar_report=calendar_report,
        digest_markdown=append_markdown,
        markdown_path=markdown_path,
        text_path=text_path,
        html_path=html_path,
    )
    footer = "_Generated at: 18/08/2026 00:00_"
    assert markdown_path.read_text(encoding="utf-8") == appended
    for path in [markdown_path, text_path]:
        content = path.read_text(encoding="utf-8")
        assert content.rstrip().endswith(footer)
        assert "---" in [line.strip() for line in content.splitlines()]
        assert "***" in content
        assert "_ _ _" in content
    html = html_path.read_text(encoding="utf-8")
    assert "<hr>" in html
    assert (
        html.split("</main>")[0].rstrip().endswith("<p><em>Generated at: 18/08/2026 00:00</em></p>")
    )
    default = build_report_markdown({}, [], **{**options, "compact": False})
    assert (
        cli.compose_report_markdown(default, append_markdown)
        == default + "\n" + append_markdown + "\n"
    )


def test_as_of_freezes_calendar_day_across_midnight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "fetch_calendar_events", Mock(return_value={"events": []}))
    assert (
        cli.main(
            [
                "--calendar-account",
                "fixture=Fixture",
                "--timezone",
                "America/Sao_Paulo",
                "--as-of",
                "2026-10-01T23:59:00-03:00",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    report = (tmp_path / "daily_calendar_2026-10-01.md").read_text(encoding="utf-8")
    assert "01/10" in report
    assert "02/10" in report
    assert "03/10" not in report


def test_as_of_rejects_naive_timestamp_before_calendar_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = Mock()
    monkeypatch.setattr(cli, "fetch_calendar_events", fetch)
    assert (
        cli.main(
            [
                "--calendar-account",
                "fixture=Fixture",
                "--timezone",
                "UTC",
                "--as-of",
                "2026-10-01T23:59:00",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 1
    )
    fetch.assert_not_called()
