from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path


class BotStatus(Enum):
    HUMAN = "human"
    BOT = "bot"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Author:
    id: str | None
    name: str | None


@dataclass(frozen=True)
class SourceMessage:
    channel_id: str
    ts: str
    thread_ts: str | None
    author: Author
    text: str
    bot_status: BotStatus
    in_window: bool


@dataclass(frozen=True)
class SourceThread:
    root_ts: str
    messages: Iterator[SourceMessage]


@dataclass(frozen=True)
class SchemaCapabilities:
    message_columns: frozenset[str]
    user_columns: frozenset[str]
    has_users_table: bool


def iter_source_threads(
    *,
    database_path: Path,
    channel_id: str,
    start: datetime,
    end: datetime,
) -> Generator[SourceThread]:
    database_path = database_path.expanduser()
    if not database_path.exists():
        raise ValueError(f"database not found: {database_path}")

    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        capabilities = inspect_schema(db)
        required = {"channel_id", "ts", "text"}
        if not required.issubset(capabilities.message_columns):
            raise ValueError("messages table must include channel_id, ts, and text columns")
        for root_ts in query_thread_roots(
            db, capabilities, channel_id, start.timestamp(), end.timestamp()
        ):
            yield SourceThread(
                root_ts=root_ts,
                messages=iter_thread_messages(
                    db, capabilities, channel_id, root_ts, start.timestamp(), end.timestamp()
                ),
            )


def query_thread_roots(
    db: sqlite3.Connection,
    capabilities: SchemaCapabilities,
    channel_id: str,
    start: float,
    end: float,
) -> Iterator[str]:
    thread = thread_expression(capabilities)
    deletion_filter = deletion_clause(capabilities)
    cursor = db.execute(
        f"""
        SELECT {thread} AS root_ts, MAX(CAST(m.ts AS REAL)) AS latest_activity
        FROM messages m
        WHERE m.channel_id = ?
          AND CAST(m.ts AS REAL) >= ? AND CAST(m.ts AS REAL) < ?
          AND m.text IS NOT NULL AND TRIM(m.text) != ''
          {deletion_filter}
        GROUP BY root_ts
        ORDER BY latest_activity DESC, root_ts DESC
        """,
        (channel_id, start, end),
    )
    for row in cursor:
        yield validate_slack_timestamp(str(row["root_ts"]))


def iter_thread_messages(
    db: sqlite3.Connection,
    capabilities: SchemaCapabilities,
    channel_id: str,
    root_ts: str,
    start: float,
    end: float,
) -> Iterator[SourceMessage]:
    selected, user_join = selection(capabilities)
    thread = thread_expression(capabilities)
    deletion_filter = deletion_clause(capabilities)
    cursor = db.execute(
        f"""
        SELECT {selected},
               CASE WHEN CAST(m.ts AS REAL) >= ? AND CAST(m.ts AS REAL) < ?
                    THEN 1 ELSE 0 END AS in_window
        FROM messages m
        {user_join}
        WHERE m.channel_id = ?
          AND (m.ts = ? OR ({thread} = ? AND CAST(m.ts AS REAL) >= ? AND CAST(m.ts AS REAL) < ?))
          AND m.text IS NOT NULL AND TRIM(m.text) != ''
          {deletion_filter}
        ORDER BY CAST(m.ts AS REAL), m.ts
        """,
        (start, end, channel_id, root_ts, root_ts, start, end),
    )
    for row in cursor:
        yield adapt_row(row, in_window=bool(row["in_window"]))


def thread_expression(capabilities: SchemaCapabilities) -> str:
    if "thread_ts" not in capabilities.message_columns:
        return "m.ts"
    return (
        "CASE WHEN m.thread_ts IS NULL OR TRIM(m.thread_ts) = '' "
        "OR m.thread_ts = m.ts THEN m.ts ELSE m.thread_ts END"
    )


def deletion_clause(capabilities: SchemaCapabilities) -> str:
    if "deleted_ts" not in capabilities.message_columns:
        return ""
    return "AND (m.deleted_ts IS NULL OR TRIM(m.deleted_ts) = '')"


def inspect_schema(db: sqlite3.Connection) -> SchemaCapabilities:
    tables = {
        str(row["name"])
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    return SchemaCapabilities(
        message_columns=frozenset(table_columns(db, "messages")),
        user_columns=frozenset(table_columns(db, "users")) if "users" in tables else frozenset(),
        has_users_table="users" in tables,
    )


def table_columns(db: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in db.execute(f"PRAGMA table_info({table_name})")}


def selection(capabilities: SchemaCapabilities) -> tuple[str, str]:
    columns = capabilities.message_columns
    user_column = "m.user_id" if "user_id" in columns else "NULL"
    thread_column = "m.thread_ts" if "thread_ts" in columns else "NULL"
    subtype_column = "m.subtype" if "subtype" in columns else "NULL"
    bot_id_column = "m.bot_id" if "bot_id" in columns else "NULL"
    raw_json_column = "m.raw_json" if "raw_json" in columns else "NULL"
    user_name_column = "NULL"
    user_is_bot_column = "NULL"
    user_join = ""
    if capabilities.has_users_table and "user_id" in columns and "id" in capabilities.user_columns:
        names = [
            column
            for column in ("display_name", "real_name", "name")
            if column in capabilities.user_columns
        ]
        if names:
            values = ", ".join(f"NULLIF(TRIM(u.{column}), '')" for column in names)
            user_name_column = f"COALESCE({values})"
        if "is_bot" in capabilities.user_columns:
            user_is_bot_column = "u.is_bot"
        workspace_join = (
            " AND u.workspace_id = m.workspace_id"
            if "workspace_id" in columns and "workspace_id" in capabilities.user_columns
            else ""
        )
        user_join = f"LEFT JOIN users u ON u.id = m.user_id{workspace_join}"
    selected = (
        f"m.channel_id, m.ts, {user_column} AS user_id, "
        f"{user_name_column} AS user_name, m.text, {thread_column} AS thread_ts, "
        f"{subtype_column} AS subtype, {bot_id_column} AS bot_id, "
        f"{raw_json_column} AS raw_json, {user_is_bot_column} AS user_is_bot"
    )
    return selected, user_join


def adapt_row(row: sqlite3.Row, *, in_window: bool) -> SourceMessage:
    ts = validate_slack_timestamp(str(row["ts"]))
    thread_ts = validate_slack_timestamp(str(row["thread_ts"])) if row["thread_ts"] else None
    return SourceMessage(
        channel_id=str(row["channel_id"]),
        ts=ts,
        thread_ts=thread_ts,
        author=Author(
            id=str(row["user_id"]) if row["user_id"] is not None else None,
            name=str(row["user_name"]) if row["user_name"] is not None else None,
        ),
        text=str(row["text"]),
        bot_status=classify_bot(row),
        in_window=in_window,
    )


def validate_slack_timestamp(value: str) -> str:
    try:
        if Decimal(value) < 0:
            raise ValueError
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid Slack timestamp: {value!r}") from exc
    return value


def classify_bot(row: sqlite3.Row) -> BotStatus:
    keys = set(row.keys())
    if "bot_id" in keys and row["bot_id"]:
        return BotStatus.BOT
    if "subtype" in keys and row["subtype"] == "bot_message":
        return BotStatus.BOT
    if "raw_json" in keys and row["raw_json"]:
        try:
            payload = json.loads(str(row["raw_json"]))
        except json.JSONDecodeError, TypeError:
            payload = {}
        if (
            payload.get("bot_id")
            or payload.get("bot_profile")
            or payload.get("subtype") == "bot_message"
        ):
            return BotStatus.BOT
    if "user_is_bot" in keys and row["user_is_bot"] is not None:
        return BotStatus.BOT if bool(row["user_is_bot"]) else BotStatus.HUMAN
    return BotStatus.UNKNOWN
