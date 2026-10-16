from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .cleanup import TextCleaner
from .references import normalize_workspace_url
from .slacrawl import iter_source_threads
from .transcript import iter_thread_records


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        timezone = parse_timezone(args.timezone)
        workspace_url = normalize_workspace_url(args.workspace_url)
        date_range = resolve_date_range(args, timezone)
        source_threads = iter_source_threads(
            database_path=args.database,
            channel_id=args.channel,
            start=date_range.start,
            end=date_range.end,
        )
        records = iter_thread_records(
            source_threads,
            include_bots=args.include_bots,
            cleaner=TextCleaner.with_default_secret_scanner(),
            limit=args.limit,
            workspace_url=workspace_url,
            timezone=timezone,
        )
        for record in records:
            print(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        return 0
    except BrokenPipeError:
        return 1
    except Exception as exc:
        print(f"slack-summary: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slack-summary",
        description="Extract one Slack channel over a time window as threaded JSON Lines.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=env_path("SLACK_SUMMARY_DATABASE"),
        required=env_path("SLACK_SUMMARY_DATABASE") is None,
        help="Path to a read-only slacrawl SQLite database. Env: SLACK_SUMMARY_DATABASE.",
    )
    parser.add_argument(
        "--channel",
        type=nonempty_string,
        default=env_string("SLACK_SUMMARY_CHANNEL"),
        required=env_string("SLACK_SUMMARY_CHANNEL") is None,
        help="Slack channel id to summarize. Env: SLACK_SUMMARY_CHANNEL.",
    )
    parser.add_argument(
        "--workspace-url",
        type=nonempty_string,
        default=env_string("SLACK_SUMMARY_WORKSPACE_URL"),
        required=env_string("SLACK_SUMMARY_WORKSPACE_URL") is None,
        help="Slack workspace URL used for message links. Env: SLACK_SUMMARY_WORKSPACE_URL.",
    )
    parser.add_argument(
        "--timezone",
        type=nonempty_string,
        default=env_string("TZ"),
        required=env_string("TZ") is None,
        help="IANA timezone for input boundaries and output. Env: TZ.",
    )
    parser.add_argument("--start", help="Start as a local date or ISO datetime.")
    parser.add_argument("--end", help="Exclusive end as a local date or ISO datetime.")
    parser.add_argument(
        "--days",
        type=positive_int,
        default=os.environ.get("SLACK_SUMMARY_DAYS", "1"),
        help="Window size when --start is omitted. Env: SLACK_SUMMARY_DAYS.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=os.environ.get("SLACK_SUMMARY_LIMIT", "500"),
        help="Maximum complete threads; omitted threads do not count. Env: SLACK_SUMMARY_LIMIT.",
    )
    parser.add_argument(
        "--include-bots",
        action=argparse.BooleanOptionalAction,
        default=env_bool("SLACK_SUMMARY_INCLUDE_BOTS", False),
        help="Include bot-authored messages. Env: SLACK_SUMMARY_INCLUDE_BOTS.",
    )
    return parser


def nonempty_string(value: str) -> str:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("must not be empty")
    return value


def env_string(name: str) -> str | None:
    value = os.environ.get(name)
    return nonempty_string(value) if value is not None else None


def env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown IANA timezone: {value}") from exc


def resolve_date_range(args: argparse.Namespace, timezone: ZoneInfo) -> DateRange:
    end = parse_moment(args.end, timezone) if args.end else datetime.now(timezone)
    start = parse_moment(args.start, timezone) if args.start else end - timedelta(days=args.days)
    if start >= end:
        raise ValueError("--start must be before --end")
    return DateRange(start=start, end=end)


def parse_moment(value: str, timezone: ZoneInfo) -> datetime:
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=timezone)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed
