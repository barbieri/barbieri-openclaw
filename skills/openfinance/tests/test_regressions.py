import argparse
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from openfinance_tools.common import connect
from openfinance_tools.patterns import main as patterns_main
from openfinance_tools.patterns import subtract_months
from openfinance_tools.summary import main as summary_main
from openfinance_tools.summary import resolve_dates


def test_subtract_months_uses_last_valid_day() -> None:
    assert subtract_months(date(2026, 5, 31), 1) == date(2026, 4, 30)


def test_patterns_rejects_unrepresentable_month_range_without_traceback(
    capsys: pytest.CaptureFixture,
) -> None:
    with pytest.raises(SystemExit):
        patterns_main(["--months", "120000"])

    error = capsys.readouterr().err
    assert "--months must be no greater than" in error
    assert "Traceback" not in error


def test_connect_handles_uri_characters_in_database_path(tmp_path: Path) -> None:
    database_path = tmp_path / "finance?archive.db"
    with sqlite3.connect(database_path) as database:
        database.execute("CREATE TABLE marker (value INTEGER)")
        database.execute("INSERT INTO marker VALUES (42)")

    with connect(database_path) as database:
        value = database.execute("SELECT value FROM marker").fetchone()[0]

    assert value == 42


def test_resolve_dates_reports_invalid_iso_date() -> None:
    args = argparse.Namespace(period=None, from_date="2026-02-30", to_date="2026-03-01")

    with pytest.raises(SystemExit, match="invalid date"):
        resolve_dates(args)


def test_resolve_dates_rejects_conflicting_selectors() -> None:
    args = argparse.Namespace(
        period="this-month",
        from_date="2026-01-01",
        to_date="2026-01-31",
    )

    with pytest.raises(SystemExit, match="either --period or --from and --to"):
        resolve_dates(args)


def test_credit_card_mode_applies_minimum_amount(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    database_path = tmp_path / "finance.db"
    today = date.today()
    boundary = subtract_months(today, 1)
    with sqlite3.connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE accounts (id INTEGER, name TEXT);
            CREATE TABLE credit_card_bills (
              id INTEGER,
              account_id INTEGER,
              due_date TEXT,
              total_amount_cents INTEGER
            );
            INSERT INTO accounts VALUES
              (1, 'Below threshold'),
              (2, 'Included'),
              (3, 'Boundary');
            """
        )
        database.executemany(
            "INSERT INTO credit_card_bills VALUES (?, ?, ?, ?)",
            [
                (1, 1, today.isoformat(), 19900),
                (2, 2, today.isoformat(), 20000),
                (3, 3, boundary.isoformat(), 50000),
            ],
        )

    assert (
        patterns_main(
            ["--db", str(database_path), "--months", "1", "--min-amount", "200", "--credit-cards"]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Included" in output
    assert "Boundary" in output
    assert "Below threshold" not in output


def test_summary_includes_transaction_at_end_of_requested_day(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    database_path = tmp_path / "finance.db"
    requested_date = date(2026, 8, 18)
    with sqlite3.connect(database_path) as database:
        database.executescript(
            """
            CREATE TABLE transactions (
              id INTEGER,
              occurred_at TEXT,
              amount_cents INTEGER,
              description TEXT
            );
            CREATE TABLE entry_annotations (
              entry_type TEXT,
              entry_id INTEGER,
              category_id INTEGER
            );
            CREATE TABLE annotation_categories (id INTEGER, name TEXT);
            INSERT INTO transactions VALUES
              (1, '2026-08-18T23:59:59Z', 10000, 'End boundary'),
              (2, '2026-08-18T00:00:00+00:00', 10000, 'Offset start'),
              (3, '2026-08-18T00:00:00.000001Z', 10000, 'Fractional start'),
              (4, '2026-08-19T00:00:00+00:00', 10000, 'Offset next day'),
              (5, '2026-08-19T00:00:00.000001Z', 10000, 'Fractional next day');
            """
        )

    assert (
        summary_main(
            [
                "--db",
                str(database_path),
                "--from",
                requested_date.isoformat(),
                "--to",
                requested_date.isoformat(),
                "--min-amount",
                "0",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "End boundary" in output
    assert "Offset start" in output
    assert "Fractional start" in output
    assert "Offset next day" not in output
    assert "Fractional next day" not in output
    assert "R$ 100.00" in output


def test_summary_reports_missing_schema_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    database_path = tmp_path / "empty.db"
    with sqlite3.connect(database_path):
        pass

    assert summary_main(["--db", str(database_path), "--period", "this-month"]) == 1

    error = capsys.readouterr().err
    assert "no such table: transactions" in error
    assert "Traceback" not in error


def test_summary_reports_date_overflow_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    database_path = tmp_path / "empty.db"
    with sqlite3.connect(database_path):
        pass

    assert (
        summary_main(
            [
                "--db",
                str(database_path),
                "--from",
                "9999-12-31",
                "--to",
                "9999-12-31",
            ]
        )
        == 1
    )

    error = capsys.readouterr().err
    assert "date value out of range" in error
    assert "Traceback" not in error
