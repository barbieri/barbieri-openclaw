from __future__ import annotations

import argparse
import json
import locale
import os
import subprocess
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from daily_calendar.email import compose_report_markdown, markdown_to_html, markdown_to_plain
from daily_calendar.report import (
    CalendarReport,
    CalendarSource,
    build_calendar_report,
    event_start_value,
)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except (
        OSError,
        ValueError,
        locale.Error,
        ZoneInfoNotFoundError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"daily-calendar: {exc}", file=sys.stderr)
        return 1


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    append_markdown = (
        Path(args.append_markdown_file).read_text(encoding="utf-8")
        if args.append_markdown_file is not None
        else ""
    )
    locale.setlocale(locale.LC_TIME, "")
    timezone = ZoneInfo(args.timezone)
    sources = parse_calendar_sources(args.calendar_account, os.getenv("DAILY_CALENDAR_ACCOUNTS"))
    holidays = load_holidays(args.holidays_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=timezone)
    if args.as_of is not None:
        as_of = datetime.fromisoformat(args.as_of)
        if as_of.tzinfo is None:
            raise ValueError("--as-of requires a timezone-aware timestamp")
        now = as_of.astimezone(timezone)
    fetch_start, fetch_end = calendar_fetch_range(
        now.date(),
        calendar_days=args.calendar_days,
        holiday_days=args.holiday_days,
        has_holidays=bool(holidays),
    )
    events_by_account = {
        source.account: fetch_calendar_events(
            args.gog_bin,
            source.account,
            start=fetch_start,
            end=fetch_end,
            timezone=timezone,
        )
        for source in sources
    }

    calendar_report = build_calendar_report(
        events_by_account,
        sources,
        now=now,
        timezone=timezone,
        holidays=holidays,
        calendar_days=args.calendar_days,
        holiday_days=args.holiday_days,
        include_chat_instructions=args.include_chat_instructions,
        compact=args.compact,
    )

    output_stem = output_dir / f"daily_calendar_{now.strftime('%Y-%m-%d')}"
    markdown_path = output_stem.with_suffix(".md")
    text_path = output_stem.with_suffix(".email.txt")
    html_path = output_stem.with_suffix(".html")

    write_report_files(
        calendar_report=calendar_report,
        digest_markdown=append_markdown,
        markdown_path=markdown_path,
        text_path=text_path,
        html_path=html_path,
    )

    if args.send_email:
        send_email(
            gog_bin=args.gog_bin,
            gmail_account=args.gmail_account,
            to=args.to,
            subject=args.subject or f"Daily calendar - {now.strftime('%d/%m/%Y')}",
            text_path=text_path,
            html_path=html_path,
            dry_run=args.dry_run,
        )

    print(markdown_path)
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and optionally email a daily calendar report."
    )
    parser.add_argument(
        "--calendar-account",
        action="append",
        default=[],
        metavar="ACCOUNT=LABEL",
        help="Calendar account alias and display label. Repeatable.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("DAILY_CALENDAR_OUTPUT_DIR", "./reports"),
        help="Directory for generated .md, .email.txt, and .html files.",
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("TZ"),
        required=os.getenv("TZ") is None,
        help="Required IANA timezone used for date grouping. Env: TZ.",
    )
    parser.add_argument(
        "--as-of",
        help="Timezone-aware ISO 8601 timestamp for the report day; defaults to the current time.",
    )
    parser.add_argument(
        "--calendar-days",
        type=int,
        default=2,
        help="Number of days to show in the main daily section.",
    )
    parser.add_argument(
        "--holiday-days",
        type=int,
        default=28,
        help="Number of days to inspect for configured holidays.",
    )
    parser.add_argument(
        "--holidays-file",
        default=os.getenv("DAILY_CALENDAR_HOLIDAYS_FILE"),
        help="JSON object mapping YYYY-MM-DD to holiday label.",
    )
    parser.add_argument(
        "--gog-bin",
        default=os.getenv("DAILY_CALENDAR_GOG_BIN", "gog"),
        help="gog executable path.",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        default=os.getenv("DAILY_CALENDAR_SEND_EMAIL") == "1",
        help="Send the generated report with gog gmail send.",
    )
    parser.add_argument(
        "--gmail-account",
        default=os.getenv("DAILY_CALENDAR_GMAIL_ACCOUNT"),
        help="gog Gmail account alias used for sending.",
    )
    parser.add_argument(
        "--to",
        default=os.getenv("DAILY_CALENDAR_TO"),
        help="Comma-separated email recipients.",
    )
    parser.add_argument(
        "--subject",
        default=os.getenv("DAILY_CALENDAR_SUBJECT"),
        help="Email subject. Defaults to a date-based subject.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DAILY_CALENDAR_DRY_RUN") == "1",
        help="Pass --dry-run to gog when sending email.",
    )
    parser.add_argument(
        "--include-chat-instructions",
        action="store_true",
        help="Include chat-only cancel/reschedule instructions in the saved Markdown report.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Omit report separators and legend, and place generated-at at the end.",
    )
    parser.add_argument(
        "--append-markdown-file",
        metavar="PATH",
        help="Append UTF-8 Markdown before the compact footer or after the default report.",
    )
    args = parser.parse_args(argv)

    if args.calendar_days < 1:
        parser.error("--calendar-days must be at least 1")
    if args.holiday_days < 0:
        parser.error("--holiday-days must be zero or greater")
    remaining_days = (date.max - date.today()).days
    if args.calendar_days > remaining_days:
        parser.error(f"--calendar-days must be no greater than {remaining_days}")
    if args.holiday_days >= remaining_days:
        parser.error(f"--holiday-days must be less than {remaining_days}")

    if not args.calendar_account and not os.getenv("DAILY_CALENDAR_ACCOUNTS"):
        parser.error("provide --calendar-account or DAILY_CALENDAR_ACCOUNTS")
    if args.send_email and not args.gmail_account:
        parser.error("--send-email requires --gmail-account or DAILY_CALENDAR_GMAIL_ACCOUNT")
    if args.send_email and not args.to:
        parser.error("--send-email requires --to or DAILY_CALENDAR_TO")

    return args


def parse_calendar_sources(cli_values: list[str], env_value: str | None) -> list[CalendarSource]:
    raw_values = list(cli_values)
    if env_value:
        raw_values.extend(item.strip() for item in env_value.split(",") if item.strip())

    sources: list[CalendarSource] = []
    accounts: set[str] = set()
    for raw_value in raw_values:
        account, separator, label = raw_value.partition("=")
        if not separator or not account.strip() or not label.strip():
            raise ValueError(f"invalid calendar account entry: {raw_value!r}")
        account = account.strip()
        if account in accounts:
            raise ValueError(f"duplicate calendar account: {account!r}")
        accounts.add(account)
        sources.append(CalendarSource(account=account, label=label.strip()))
    if not sources:
        raise ValueError("provide at least one calendar account")
    return sources


def load_holidays(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    with Path(path).open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError("holidays file must be a JSON object")

    holidays: dict[str, str] = {}
    for key, value in data.items():
        if (
            not isinstance(key, str)
            or not isinstance(value, str)
            or not value.strip()
            or any(unicodedata.category(character) in {"Cc", "Zl", "Zp"} for character in value)
        ):
            raise ValueError("holidays file entries must map dates to non-empty single-line labels")
        try:
            parsed_date = date.fromisoformat(key)
        except ValueError as exc:
            raise ValueError(f"holidays file contains an invalid date: {key!r}") from exc
        if key != parsed_date.isoformat():
            raise ValueError(f"holidays file date must use YYYY-MM-DD: {key!r}")
        holidays[key] = value
    return holidays


def calendar_fetch_range(
    today: date, *, calendar_days: int, holiday_days: int, has_holidays: bool
) -> tuple[date, date]:
    days = max(calendar_days, holiday_days + 1 if has_holidays else 0)
    return today, today + timedelta(days=days)


def fetch_calendar_events(
    gog_bin: str,
    account: str,
    *,
    start: date,
    end: date,
    timezone: ZoneInfo,
) -> dict:
    result = subprocess.run(
        [
            gog_bin,
            "calendar",
            "list",
            "-a",
            account,
            "--from",
            start.isoformat(),
            "--to",
            end.isoformat(),
            "--timezone",
            timezone.key,
            "--all-pages",
            "--no-input",
            "--json",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return parse_calendar_response(result.stdout)


def parse_calendar_response(raw_response: str) -> dict:
    data = json.loads(raw_response)
    if not isinstance(data, dict):
        raise ValueError("calendar response must be a JSON object")
    events = data.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError("calendar response must contain an event list")
    for event in events:
        validate_calendar_event(event)
    return data


def validate_calendar_event(event: dict) -> None:
    for field in ("start", "organizer", "creator"):
        if field in event and not isinstance(event[field], dict):
            raise ValueError(f"calendar response event {field!r} must be an object")

    event_start_value(event)

    attendees = event.get("attendees", [])
    if not isinstance(attendees, list) or not all(isinstance(item, dict) for item in attendees):
        raise ValueError("calendar response event attendees must be an object list")
    for attendee in attendees:
        if "self" in attendee and not isinstance(attendee["self"], bool):
            raise ValueError("calendar response attendee self must be a boolean")
        if "responseStatus" in attendee and not isinstance(attendee["responseStatus"], str):
            raise ValueError("calendar response attendee responseStatus must be a string")

    for field in ("organizer", "creator"):
        owner = event.get(field, {})
        if "self" in owner and not isinstance(owner["self"], bool):
            raise ValueError(f"calendar response event {field}.self must be a boolean")

    for field in ("id", "iCalUID", "summary", "eventType", "recurringEventId"):
        if field in event and not isinstance(event[field], str):
            raise ValueError(f"calendar response event {field!r} must be a string")


def write_report_files(
    *,
    calendar_report: CalendarReport,
    digest_markdown: str = "",
    markdown_path: Path,
    text_path: Path,
    html_path: Path,
) -> None:
    body, footer = calendar_report.body, calendar_report.footer
    markdown = compose_report_markdown(body, digest_markdown, footer=footer)
    outputs = {
        markdown_path: markdown,
        text_path: markdown_to_plain(body, digest_markdown, footer=footer),
        html_path: markdown_to_html(body, digest_markdown, footer=footer),
    }
    with tempfile.TemporaryDirectory(prefix=".daily-calendar-", dir=markdown_path.parent) as temp:
        temp_dir = Path(temp)
        staged_paths: dict[Path, Path] = {}
        for destination, content in outputs.items():
            staged_path = temp_dir / destination.name
            staged_path.write_text(content, encoding="utf-8")
            staged_paths[destination] = staged_path
        for destination, staged_path in staged_paths.items():
            staged_path.replace(destination)


def send_email(
    *,
    gog_bin: str,
    gmail_account: str,
    to: str,
    subject: str,
    text_path: Path,
    html_path: Path,
    dry_run: bool,
) -> None:
    command = [
        gog_bin,
        "gmail",
        "send",
        "-a",
        gmail_account,
        "--to",
        to,
        "--subject",
        subject,
        "--body-file",
        str(text_path),
        "--body-html-file",
        str(html_path),
        "--no-input",
    ]
    if dry_run:
        command.insert(3, "--dry-run")

    subprocess.run(command, check=True)
