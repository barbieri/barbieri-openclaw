from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date

from openfinance_tools.common import (
    add_db_argument,
    connect,
    date_prefix_bounds,
    period_to_dates,
    print_rows,
    resolve_db,
)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except (OSError, OverflowError, sqlite3.Error) as exc:
        print(f"openfinance-summary: {exc}", file=sys.stderr)
        return 1


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize OpenFinance transactions.")
    add_db_argument(parser)
    parser.add_argument(
        "--period",
        choices=[
            "this-week",
            "last-week",
            "this-month",
            "last-month",
            "last-7-days",
            "last-30-days",
        ],
        help="Named period to summarize.",
    )
    parser.add_argument("--from", dest="from_date", help="Start date, YYYY-MM-DD.")
    parser.add_argument("--to", dest="to_date", help="End date, YYYY-MM-DD.")
    parser.add_argument("--min-amount", type=int, default=100, help="Minimum amount in BRL.")
    args = parser.parse_args(argv)

    if args.min_amount < 0:
        parser.error("--min-amount must be zero or greater")

    from_date, to_date = resolve_dates(args)
    min_amount_cents = args.min_amount * 100
    start, end = date_prefix_bounds(from_date, to_date)

    with connect(resolve_db(args.db)) as db:
        summary = db.execute(
            """
            SELECT
              printf(
                'R$ %.2f',
                SUM(CASE WHEN amount_cents > 0 THEN amount_cents ELSE 0 END) / 100.0
              ) AS Income,
              printf(
                'R$ %.2f',
                -SUM(CASE WHEN amount_cents < 0 THEN amount_cents ELSE 0 END) / 100.0
              ) AS Expenses,
              printf('R$ %.2f', SUM(amount_cents) / 100.0) AS Net
            FROM transactions
            WHERE occurred_at >= ?
              AND occurred_at < ?
              AND ABS(amount_cents) >= ?
            """,
            (start, end, min_amount_cents),
        ).fetchall()
        categories = db.execute(
            """
            SELECT
              COALESCE(ac.name, '(no category)') AS Category,
              COUNT(*) AS Count,
              printf('R$ %.2f', -SUM(t.amount_cents) / 100.0) AS Total
            FROM transactions t
            LEFT JOIN entry_annotations ea
              ON ea.entry_type = 'transaction' AND ea.entry_id = t.id
            LEFT JOIN annotation_categories ac ON ea.category_id = ac.id
            WHERE t.occurred_at >= ?
              AND t.occurred_at < ?
              AND t.amount_cents < 0
              AND ABS(t.amount_cents) >= ?
            GROUP BY ac.name
            ORDER BY SUM(t.amount_cents) ASC
            LIMIT 10
            """,
            (start, end, min_amount_cents),
        ).fetchall()
        transactions = db.execute(
            """
            SELECT
              substr(t.occurred_at, 1, 10) AS Date,
              printf('R$ %.2f', t.amount_cents / 100.0) AS Amount,
              substr(COALESCE(t.description, ''), 1, 40) AS Description,
              COALESCE(ac.name, '') AS Category
            FROM transactions t
            LEFT JOIN entry_annotations ea
              ON ea.entry_type = 'transaction' AND ea.entry_id = t.id
            LEFT JOIN annotation_categories ac ON ea.category_id = ac.id
            WHERE t.occurred_at >= ?
              AND t.occurred_at < ?
              AND ABS(t.amount_cents) >= ?
            ORDER BY ABS(t.amount_cents) DESC
            LIMIT 20
            """,
            (start, end, min_amount_cents),
        ).fetchall()

    print(f"Financial Summary: {from_date.isoformat()} to {to_date.isoformat()}")
    print(f"Minimum transaction amount: R$ {args.min_amount}")
    print_rows("Summary", ["Income", "Expenses", "Net"], summary)
    print_rows("Top Categories", ["Category", "Count", "Total"], categories)
    print_rows("Largest Transactions", ["Date", "Amount", "Description", "Category"], transactions)
    return 0


def resolve_dates(args: argparse.Namespace) -> tuple[date, date]:
    if args.period and (args.from_date or args.to_date):
        raise SystemExit("error: provide either --period or --from and --to")
    if args.period:
        return period_to_dates(args.period)
    if args.from_date and args.to_date:
        try:
            start = date.fromisoformat(args.from_date)
            end = date.fromisoformat(args.to_date)
        except ValueError as exc:
            raise SystemExit(f"error: invalid date: {exc}") from exc
        if start > end:
            raise SystemExit("error: --from must not be after --to")
        return start, end
    raise SystemExit("error: provide --period or both --from and --to")


if __name__ == "__main__":
    raise SystemExit(main())
