# OpenFinance

Small CLIs for summarizing a Brazilian Open Finance SQLite database produced by [local-openfinance](https://github.com/barbieri/local-openfinance).

The database path is never hardcoded. Provide it with `--db` or `OPENFINANCE_DB`.
Amounts intentionally use Brazilian real, BRL and `R$`.

## Commands

```bash
openfinance-summary --db /path/to/openfinance.sqlite --period this-month
openfinance-patterns --db /path/to/openfinance.sqlite --months 6
```

## Environment Variables

- `OPENFINANCE_DB`: SQLite database path.

## Validation

From the repository root:

```bash
uv run pytest skills/openfinance/tests
uv run ruff check skills/openfinance
```
