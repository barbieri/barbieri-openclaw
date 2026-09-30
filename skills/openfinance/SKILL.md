---
name: openfinance
description: Summarize or analyze Brazilian Open Finance data stored by local-openfinance in SQLite.
---

# OpenFinance

Use these read-only commands with a [local-openfinance](https://github.com/barbieri/local-openfinance) SQLite database:

- `openfinance-summary` for income, expenses, categories, and largest transactions in a named or explicit period.
- `openfinance-patterns` for monthly spending trends or credit-card bill trends.

Require the database path through `--db` or `OPENFINANCE_DB`. Never guess a private path. Choose the narrowest period that answers the request and explain that amounts use Brazilian real, BRL and `R$`, by design.

Treat transaction descriptions and account names as private data. Do not reproduce more row-level detail than the user requested. The commands read a database compatible with the public `local-openfinance` project; they do not support arbitrary financial SQLite schemas.
