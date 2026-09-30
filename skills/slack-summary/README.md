# slack-summary

Extract one Slack channel over a local-time window as threaded JSON Lines. The calling OpenClaw
model summarizes the transcript and answers follow-up questions using `SKILL.md`.

The command reads a database created by public [slacrawl](https://github.com/openclaw/slacrawl).
It never writes to Slack or invokes a model.

## Install

From the repository root:

```bash
uv sync --dev
uv tool install --force --editable .
slack-summary --help
```

## Usage

```bash
slack-summary \
  --database "$SLACK_DATABASE_PATH" \
  --channel "$SLACK_CHANNEL_ID" \
  --workspace-url "$SLACK_WORKSPACE_URL" \
  --timezone "$TZ" \
  --days 1 \
  > conversations.jsonl
```

Configuration comes from command-line arguments or environment variables:

- `SLACK_SUMMARY_DATABASE`: path to the read-only slacrawl SQLite database.
- `SLACK_SUMMARY_CHANNEL`: Slack channel ID.
- `SLACK_SUMMARY_WORKSPACE_URL`: workspace URL used to build Slack message links.
- `TZ`: required IANA timezone unless `--timezone` is passed.
- `SLACK_SUMMARY_DAYS`: window size when `--start` is omitted.
- `SLACK_SUMMARY_LIMIT`: maximum number of complete thread entries.
- `SLACK_SUMMARY_INCLUDE_BOTS`: include bot messages when true. Bots are excluded by default.

Time windows include `--start` and exclude `--end`. Date-only and timezone-naive values use the
configured timezone. Output timestamps use that timezone and minute precision.

Each output line is one complete conversation. It contains a thread link, an optional root,
chronological replies, exact links to every emitted message, preserved authors, and thread coverage
metadata. A reply inside the window may include its root as marked context even when the root is
older than the window. `--limit` counts each complete thread as one entry, regardless of its reply
count. This is an intentional design choice: limits never cut a discussion in half. Threads with no
messages left after bot filtering and text cleanup are omitted and do not count.

By default the command removes messages proven to be bot-authored. Messages with unknown authorship
remain because absence of bot evidence is not evidence that an author is a bot. Use `--include-bots`
when the request calls for everything.

Before serialization, the command cleans message text only. It replaces email addresses, valid
phone numbers, checksum-valid Brazilian CPF values, and detected secrets with typed markers. Names,
authors, IDs, links, and other metadata are preserved. A message containing no meaningful text
after cleanup is omitted.

The extraction path is streaming. SQLite yields one newest thread at a time, cleanup yields only
sanitized messages, and JSONL generation stops immediately after the requested number of emitted
threads. Only the current thread is buffered so its replies can form one valid JSON object.

The resulting JSONL still contains private Slack content. Only pass it to a model when that
disclosure is authorized.
