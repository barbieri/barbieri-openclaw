# barbieri-openclaw

Reusable OpenClaw skills backed by small, testable Python command-line tools. The project requires Python 3.14.

## Skills

- `skills/daily-calendar`: daily calendar report generator with Markdown, plain-text email, and HTML email output.
- `skills/openfinance`: OpenFinance SQLite summary and pattern CLIs.
- `skills/slack-summary`: Slack transcript extraction and conversational analysis from a local slacrawl database.

Each directory contains a `SKILL.md` for OpenClaw and a README for direct CLI use. The external data providers are public projects:

- Daily Calendar uses [gogcli](https://github.com/openclaw/gogcli).
- Slack Summary uses [slacrawl](https://github.com/openclaw/slacrawl).
- OpenFinance uses the Brazilian [local-openfinance](https://github.com/barbieri/local-openfinance) SQLite schema.

All account aliases, recipients, channel IDs, database paths, timezones, and other deployment-specific values come from command-line arguments or environment variables.

## Development

```bash
uv sync --dev
uv run pre-commit install
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pre-commit run --all-files
```

## Installed Commands

Python commands are installed for the current user with `uv tool install`:

```bash
uv tool install --force --editable .
daily-calendar --help
openfinance-summary --help
openfinance-patterns --help
slack-summary --help
```

The user-level install keeps commands available to OpenClaw, cron, and shells without activating a
virtualenv. Make sure the user bin directory reported by `uv tool update-shell` is on `PATH`.

Configure OpenClaw to discover the desired directory under `skills/`. The skill instructions invoke the installed commands and keep model reasoning in the active conversation.

## License

This project is licensed under GPL-3.0-or-later. See [LICENSE](LICENSE).
