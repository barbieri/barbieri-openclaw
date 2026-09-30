import sqlite3
from datetime import date

import pytest
from openfinance_tools.common import period_to_dates, print_rows
from openfinance_tools.patterns import subtract_months


def test_period_to_dates_last_week() -> None:
    start, end = period_to_dates("last-week", today=date(2026, 8, 18))

    assert start == date(2026, 8, 10)
    assert end == date(2026, 8, 16)


def test_lookback_periods_include_today() -> None:
    today = date(2026, 8, 18)

    assert period_to_dates("last-7-days", today=today) == (date(2026, 8, 12), today)
    assert period_to_dates("last-30-days", today=today) == (date(2026, 7, 20), today)


def test_subtract_months_clamps_day() -> None:
    assert subtract_months(date(2026, 3, 31), 1) == date(2026, 2, 28)


def test_print_rows_normalizes_control_whitespace(capsys: pytest.CaptureFixture) -> None:
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    row = database.execute(
        "SELECT ? AS Description, ? AS Amount",
        ("merchant\nforged\tcolumn\u2028another row", "R$ 10.00"),
    ).fetchone()

    print_rows("Transactions", ["Description", "Amount"], [row])

    output = capsys.readouterr().out
    assert "merchant forged column another row | R$ 10.00" in output
    assert "\t" not in output
    assert "\nforged" not in output
    assert "\u2028" not in output
