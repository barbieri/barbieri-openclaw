from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .references import local_minute, slack_href
from .slacrawl import BotStatus, SchemaCapabilities, inspect_schema, validate_slack_timestamp

MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
NOISE_SUBTYPES = {
    "bot_message",
    "channel_join",
    "channel_leave",
    "channel_archive",
    "channel_unarchive",
    "group_join",
    "group_leave",
    "huddle_thread",
    "thread_broadcast",
}
NOISE_TEXT_RE = re.compile(
    r"^(?:has joined the channel|has left the channel|set the channel topic:)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AskDismissal:
    channel_id: str
    thread_ts: str
    ask_ts: str
    dismissed_at: str


@dataclass(frozen=True)
class UnansweredAsk:
    channel_id: str
    thread_ts: str
    ask_ts: str
    text: str
    author_name: str | None
    href: str


def load_dismissed_state(path: Path | None) -> list[AskDismissal]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("dismissed state file must be a JSON object")
    entries = data.get("dismissed", [])
    if not isinstance(entries, list):
        raise ValueError("dismissed state file dismissed must be a list")
    dismissed: list[AskDismissal] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("dismissed state entries must be objects")
        dismissed.append(
            AskDismissal(
                channel_id=str(entry["channel_id"]),
                thread_ts=str(entry["thread_ts"]),
                ask_ts=str(entry["ask_ts"]),
                dismissed_at=str(entry.get("dismissed_at", "")),
            )
        )
    return dismissed


def save_dismissed_state(path: Path, dismissed: list[AskDismissal]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dismissed": [
            {
                "channel_id": item.channel_id,
                "thread_ts": item.thread_ts,
                "ask_ts": item.ask_ts,
                "dismissed_at": item.dismissed_at,
            }
            for item in dismissed
        ]
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_unanswered_asks_markdown(
    asks: list[UnansweredAsk],
    *,
    timezone,
    workspace_url: str,
) -> str:
    if not asks:
        return "## Unanswered Slack\n\nNo unanswered asks found.\n"

    lines = ["## Unanswered Slack", ""]
    for ask in asks:
        timestamp = local_minute(ask.ask_ts, timezone)
        author = ask.author_name or "Someone"
        lines.append(f"- [{timestamp}] **{author}**: {ask.text} ([open]({ask.href}))")
    lines.append("")
    return "\n".join(lines)


def find_unanswered_asks(
    *,
    database_path: Path,
    target_user_id: str,
    start_ts: float,
    end_ts: float,
    workspace_url: str,
    dismissed: list[AskDismissal],
    limit: int,
) -> list[UnansweredAsk]:
    database_path = database_path.expanduser()
    if not database_path.exists():
        raise ValueError(f"database not found: {database_path}")

    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        capabilities = inspect_schema(db)
        channel_ids = list_channel_ids(db, capabilities, start_ts, end_ts, target_user_id)
        results: list[UnansweredAsk] = []
        for channel_id in channel_ids:
            for ask in iter_channel_asks(
                db,
                capabilities,
                channel_id=channel_id,
                target_user_id=target_user_id,
                start_ts=start_ts,
                end_ts=end_ts,
                workspace_url=workspace_url,
                dismissed=dismissed,
            ):
                results.append(ask)
                if len(results) >= limit:
                    return sorted(results, key=lambda item: float(item.ask_ts), reverse=True)
        return sorted(results, key=lambda item: float(item.ask_ts), reverse=True)


def list_channel_ids(
    db: sqlite3.Connection,
    capabilities: SchemaCapabilities,
    start_ts: float,
    end_ts: float,
    target_user_id: str,
) -> list[str]:
    mention = f"<@{target_user_id}>"
    user_column = "m.user_id" if "user_id" in capabilities.message_columns else "NULL"
    cursor = db.execute(
        f"""
        SELECT DISTINCT m.channel_id
        FROM messages m
        WHERE CAST(m.ts AS REAL) >= ? AND CAST(m.ts AS REAL) < ?
          AND (
            {user_column} = ?
            OR m.text LIKE ?
            OR m.channel_id LIKE 'D%'
            OR m.channel_id LIKE 'G%'
          )
        ORDER BY m.channel_id
        """,
        (start_ts, end_ts, target_user_id, f"%{mention}%"),
    )
    return [str(row["channel_id"]) for row in cursor]


def iter_channel_asks(
    db: sqlite3.Connection,
    capabilities: SchemaCapabilities,
    *,
    channel_id: str,
    target_user_id: str,
    start_ts: float,
    end_ts: float,
    workspace_url: str,
    dismissed: list[AskDismissal],
) -> list[UnansweredAsk]:
    selected = _selection(capabilities)
    cursor = db.execute(
        f"""
        SELECT {selected}
        FROM messages m
        {_user_join(capabilities)}
        WHERE m.channel_id = ?
          AND CAST(m.ts AS REAL) >= ? AND CAST(m.ts AS REAL) < ?
          AND m.text IS NOT NULL AND TRIM(m.text) != ''
        ORDER BY CAST(m.ts AS REAL), m.ts
        """,
        (channel_id, start_ts - 7 * 24 * 3600, end_ts),
    )
    rows = [dict(row) for row in cursor]
    threads: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        root_ts = _thread_root(row)
        threads.setdefault(root_ts, []).append(row)

    unanswered: list[UnansweredAsk] = []
    for root_ts, messages in threads.items():
        for message in messages:
            if not _message_in_window(message, start_ts, end_ts):
                continue
            if not message_targets_user(message, channel_id, target_user_id):
                continue
            if is_noise_message(message):
                continue
            if classify_bot_row(message) is BotStatus.BOT:
                continue
            if user_answered_after(messages, message, target_user_id):
                continue
            if is_dismissed(dismissed, channel_id, root_ts, message, messages, target_user_id):
                continue
            unanswered.append(
                UnansweredAsk(
                    channel_id=channel_id,
                    thread_ts=root_ts,
                    ask_ts=str(message["ts"]),
                    text=str(message["text"]).strip(),
                    author_name=_author_name(message),
                    href=slack_href(
                        workspace_url,
                        channel_id,
                        str(message["ts"]),
                        root_ts if root_ts != str(message["ts"]) else None,
                    ),
                )
            )
    return unanswered


def message_targets_user(message: dict[str, object], channel_id: str, target_user_id: str) -> bool:
    if message.get("user_id") == target_user_id:
        return False
    text = str(message.get("text", ""))
    if f"<@{target_user_id}>" in text:
        return True
    if channel_id.startswith(("D", "G")):
        return bool(text.strip())
    return False


def is_noise_message(message: dict[str, object]) -> bool:
    subtype = message.get("subtype")
    if isinstance(subtype, str) and subtype in NOISE_SUBTYPES:
        return True
    text = str(message.get("text", "")).strip()
    if not text or text in {":wave:", ":slack_call:"}:
        return True
    return bool(NOISE_TEXT_RE.match(text))


def user_answered_after(
    messages: list[dict[str, object]], ask: dict[str, object], target_user_id: str
) -> bool:
    ask_ts = float(str(ask["ts"]))
    for message in messages:
        if float(str(message["ts"])) <= ask_ts:
            continue
        if message.get("user_id") == target_user_id:
            return True
    return user_reacted(ask, target_user_id)


def user_reacted(message: dict[str, object], target_user_id: str) -> bool:
    raw_json = message.get("raw_json")
    if not isinstance(raw_json, str) or not raw_json:
        return False
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return False
    reactions = payload.get("reactions", [])
    if not isinstance(reactions, list):
        return False
    for reaction in reactions:
        if not isinstance(reaction, dict):
            continue
        users = reaction.get("users", [])
        if isinstance(users, list) and target_user_id in users:
            return True
    return False


def is_dismissed(
    dismissed: list[AskDismissal],
    channel_id: str,
    thread_ts: str,
    ask: dict[str, object],
    messages: list[dict[str, object]],
    target_user_id: str,
) -> bool:
    ask_ts = str(ask["ts"])
    for entry in dismissed:
        if entry.channel_id != channel_id or entry.thread_ts != thread_ts:
            continue
        if entry.ask_ts != ask_ts:
            continue
        return not _thread_re_asked_after(
            messages,
            channel_id=channel_id,
            after_ts=float(str(entry.ask_ts)),
            target_user_id=target_user_id,
        )
    return False


def _thread_re_asked_after(
    messages: list[dict[str, object]],
    *,
    channel_id: str,
    after_ts: float,
    target_user_id: str,
) -> bool:
    for message in messages:
        if float(str(message["ts"])) <= after_ts:
            continue
        if message_targets_user(message, channel_id, target_user_id):
            return True
    return False


def _message_in_window(message: dict[str, object], start_ts: float, end_ts: float) -> bool:
    ts = float(str(message["ts"]))
    return start_ts <= ts < end_ts


def _thread_root(row: dict[str, object]) -> str:
    thread_ts = row.get("thread_ts")
    ts = str(row["ts"])
    if isinstance(thread_ts, str) and thread_ts and thread_ts != ts:
        return validate_slack_timestamp(thread_ts)
    return validate_slack_timestamp(ts)


def classify_bot_row(row: dict[str, object]) -> BotStatus:
    if row.get("bot_id"):
        return BotStatus.BOT
    subtype = row.get("subtype")
    if subtype == "bot_message":
        return BotStatus.BOT
    raw_json = row.get("raw_json")
    if isinstance(raw_json, str) and raw_json:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            payload = {}
        if (
            payload.get("bot_id")
            or payload.get("bot_profile")
            or payload.get("subtype") == "bot_message"
        ):
            return BotStatus.BOT
    user_is_bot = row.get("user_is_bot")
    if user_is_bot is not None:
        return BotStatus.BOT if bool(user_is_bot) else BotStatus.HUMAN
    return BotStatus.UNKNOWN


def _author_name(row: dict[str, object]) -> str | None:
    value = row.get("user_name")
    return str(value) if value else None


def _selection(capabilities: SchemaCapabilities) -> str:
    columns = capabilities.message_columns
    user_column = "m.user_id" if "user_id" in columns else "NULL"
    thread_column = "m.thread_ts" if "thread_ts" in columns else "NULL"
    subtype_column = "m.subtype" if "subtype" in columns else "NULL"
    bot_id_column = "m.bot_id" if "bot_id" in columns else "NULL"
    raw_json_column = "m.raw_json" if "raw_json" in columns else "NULL"
    user_name_column = "NULL"
    user_is_bot_column = "NULL"
    if capabilities.has_users_table and "user_id" in columns:
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
    return (
        f"m.channel_id, m.ts, {user_column} AS user_id, {user_name_column} AS user_name, "
        f"m.text, {thread_column} AS thread_ts, {subtype_column} AS subtype, "
        f"{bot_id_column} AS bot_id, {raw_json_column} AS raw_json, "
        f"{user_is_bot_column} AS user_is_bot"
    )


def _user_join(capabilities: SchemaCapabilities) -> str:
    columns = capabilities.message_columns
    if not capabilities.has_users_table or "user_id" not in columns:
        return ""
    workspace_join = (
        " AND u.workspace_id = m.workspace_id"
        if "workspace_id" in columns and "workspace_id" in capabilities.user_columns
        else ""
    )
    return f"LEFT JOIN users u ON u.id = m.user_id{workspace_join}"
