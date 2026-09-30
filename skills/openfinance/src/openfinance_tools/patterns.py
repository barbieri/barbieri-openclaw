from __future__ import annotations

import argparse
import calendar
import sqlite3
import sys
from datetime import date

from openfinance_tools.common import (
    add_db_argument,
    connect,
    date_prefix_bounds,
    print_rows,
    resolve_db,
)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except (OSError, OverflowError, sqlite3.Error) as exc:
        print(f"openfinance-patterns: {exc}", file=sys.stderr)
        return 1


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze OpenFinance spending patterns.")
    add_db_argument(parser)
    parser.add_argument("--months", type=int, default=12, help="Lookback period in months.")
    parser.add_argument("--min-amount", type=int, default=200, help="Minimum amount in BRL.")
    parser.add_argument("--credit-cards", action="store_true", help="Show credit card bill trends.")
    args = parser.parse_args(argv)

    if args.months < 0:
        parser.error("--months must be zero or greater")
    if args.min_amount < 0:
        parser.error("--min-amount must be zero or greater")

    today = date.today()
    max_months = (today.year - 1) * 12 + today.month - 1
    if args.months > max_months:
        parser.error(f"--months must be no greater than {max_months}")
    from_date = subtract_months(today, args.months)
    start, end = date_prefix_bounds(from_date, today)
    min_amount_cents = args.min_amount * 100

    with connect(resolve_db(args.db)) as db:
        if args.credit_cards:
            rows = db.execute(
                """
                SELECT
                  strftime('%Y-%m', b.due_date) AS Month,
                  COALESCE(a.name, '') AS Account,
                  COUNT(DISTINCT b.id) AS Bills,
                  printf('R$ %.2f', AVG(b.total_amount_cents) / 100.0) AS Avg_Bill,
                  printf('R$ %.2f', MAX(b.total_amount_cents) / 100.0) AS Max_Bill
                FROM credit_card_bills b
                JOIN accounts a ON b.account_id = a.id
                WHERE b.due_date >= ?
                  AND b.due_date < ?
                  AND b.total_amount_cents >= ?
                GROUP BY Month, a.name
                ORDER BY Month DESC, a.name
                """,
                (start, end, min_amount_cents),
            ).fetchall()
            print(f"Credit Card Spending Analysis: {from_date.isoformat()} to {today.isoformat()}")
            print_rows("Monthly Bills", ["Month", "Account", "Bills", "Avg_Bill", "Max_Bill"], rows)
            return 0

        rows = db.execute(
            """
            SELECT
              strftime('%Y-%m', occurred_at) AS Month,
              COUNT(*) AS Transactions,
              printf('R$ %.2f', -SUM(amount_cents) / 100.0) AS Expenses,
              printf('R$ %.2f', -AVG(amount_cents) / 100.0) AS Avg_Transaction
            FROM transactions
            WHERE occurred_at >= ?
              AND occurred_at < ?
              AND amount_cents < 0
              AND ABS(amount_cents) >= ?
            GROUP BY strftime('%Y-%m', occurred_at)
            ORDER BY Month DESC
            """,
            (start, end, min_amount_cents),
        ).fetchall()

    print(f"Financial Pattern Analysis: {from_date.isoformat()} to {today.isoformat()}")
    print(f"Minimum transaction amount: R$ {args.min_amount}")
    print_rows(
        "Monthly Spending Trend", ["Month", "Transactions", "Expenses", "Avg_Transaction"], rows
    )
    return 0


def subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


if __name__ == "__main__":
    raise SystemExit(main())
