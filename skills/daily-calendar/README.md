# Daily Calendar

Generate a daily calendar report with public [gogcli](https://github.com/openclaw/gogcli), render it as Markdown, and optionally send it as a multipart Gmail message with:

- `text/plain`: Markdown/plain fallback
- `text/html`: formatted primary view

No account aliases, email addresses, passwords, or host-specific paths are hardcoded. Pass configuration with CLI arguments or environment variables.

## Generate A Report

```bash
daily-calendar \
  --timezone "$TZ" \
  --calendar-account "$CALENDAR_ACCOUNT=$CALENDAR_LABEL" \
  --output-dir ./reports
```

## Send Email

```bash
DAILY_CALENDAR_GMAIL_ACCOUNT="$GMAIL_ACCOUNT_ALIAS" \
DAILY_CALENDAR_TO="$REPORT_RECIPIENT" \
daily-calendar \
  --calendar-account "$CALENDAR_ACCOUNT=$CALENDAR_LABEL" \
  --output-dir ./reports \
  --send-email
```

## Environment Variables

- `DAILY_CALENDAR_ACCOUNTS`: comma-separated `account=Label` entries.
- `DAILY_CALENDAR_GMAIL_ACCOUNT`: `gog` Gmail account alias used for sending.
- `DAILY_CALENDAR_TO`: comma-separated recipients.
- `DAILY_CALENDAR_SUBJECT`: optional subject override.
- `DAILY_CALENDAR_OUTPUT_DIR`: output directory.
- `TZ`: required IANA timezone unless `--timezone` is passed.
- `LC_ALL`, `LC_TIME`, or `LANG`: standard locale selection used for weekday names.
- `DAILY_CALENDAR_GOG_BIN`: `gog` executable, default `gog`.
- `DAILY_CALENDAR_HOLIDAYS_FILE`: optional JSON object mapping `YYYY-MM-DD` to holiday name.
- `DAILY_CALENDAR_SEND_EMAIL`: set to `1` to send the generated report.
- `DAILY_CALENDAR_DRY_RUN`: set to `1` to pass `--dry-run` to `gog gmail send`.

## Holiday File

```json
{
  "2026-12-25": "Christmas"
}
```

## Validation

From the repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pre-commit run --all-files
```
