from __future__ import annotations

import argparse
import os
import sqlite3
import unicodedata
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path


def add_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        default=os.getenv("OPENFINANCE_DB"),
        help="OpenFinance SQLite database path. Can also be set with OPENFINANCE_DB.",
    )


def resolve_db(path: str | None) -> Path:
    if not path:
        raise SystemExit("error: provide --db or OPENFINANCE_DB")
    db_path = Path(path).expanduser()
    if not db_path.exists():
        raise SystemExit(f"error: database not found: {db_path}")
    return db_path


def connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def period_to_dates(period: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if period == "this-week":
        return today - timedelta(days=today.weekday()), today
    if period == "last-week":
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if period == "this-month":
        return today.replace(day=1), today
    if period == "last-month":
        first_this_month = today.replace(day=1)
        last_previous_month = first_this_month - timedelta(days=1)
        return last_previous_month.replace(day=1), last_previous_month
    if period == "last-7-days":
        return today - timedelta(days=6), today
    if period == "last-30-days":
        return today - timedelta(days=29), today
    raise argparse.ArgumentTypeError(f"unknown period: {period}")


def date_prefix_bounds(from_date: date, to_date: date) -> tuple[str, str]:
    return from_date.isoformat(), (to_date + timedelta(days=1)).isoformat()


def print_rows(title: str, headers: Sequence[str], rows: Sequence[sqlite3.Row]) -> None:
    print("")
    print(title)
    print("-" * len(title))
    if not rows:
        print("(none)")
        return

    widths = [len(header) for header in headers]
    values = [[render_cell(row[header]) for header in headers] for row in rows]
    for row in values:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in values:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def render_cell(value: object) -> str:
    return "".join(
        " " if unicodedata.category(character) in {"Cc", "Zl", "Zp"} else character
        for character in str(value)
    )
