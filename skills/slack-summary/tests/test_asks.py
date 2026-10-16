from __future__ import annotations

import sqlite3
from pathlib import Path

from slack_summary.asks import (
    AskDismissal,
    find_unanswered_asks,
    is_dismissed,
    load_dismissed_state,
    user_answered_after,
    user_reacted,
)


def fixture_workspace_url() -> str:
    return "https://slack.example.invalid/"


def write_asks_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE messages (
              channel_id TEXT,
              ts TEXT,
              user_id TEXT,
              subtype TEXT,
              text TEXT,
              thread_ts TEXT,
              raw_json TEXT
            );
            INSERT INTO messages VALUES
              ('C1', '100.000001', 'U2', NULL,
               'Hey <@U1> can you review this?', NULL, '{}'),
              ('C1', '100.000002', 'U1', NULL,
               'Looks good', '100.000001', '{}'),
              ('C1', '100.000003', 'U2', NULL,
               '<@U1> what about the RFQ?', NULL, '{}'),
              ('D1', '100.000010', 'U2', NULL,
               'Need your sign-off', NULL, '{}'),
              ('C2', '100.000020', 'B1', 'bot_message',
               '<@U1> automated ping', NULL, '{"bot_id":"B1"}');
            """
        )


def test_find_unanswered_asks_skips_answered_and_bots(tmp_path: Path) -> None:
    db_path = tmp_path / "asks.db"
    write_asks_db(db_path)

    asks = find_unanswered_asks(
        database_path=db_path,
        target_user_id="U1",
        start_ts=0,
        end_ts=200,
        workspace_url=fixture_workspace_url(),
        dismissed=[],
        limit=10,
    )

    texts = [ask.text for ask in asks]
    assert "<@U1> what about the RFQ?" in texts
    assert "Need your sign-off" in texts
    assert "can you review this?" not in texts
    assert "automated ping" not in texts


def test_user_answered_after_reply() -> None:
    messages = [
        {"ts": "1.0", "user_id": "U2", "text": "<@U1> ping"},
        {"ts": "2.0", "user_id": "U1", "text": "done"},
    ]
    assert user_answered_after(messages, messages[0], "U1") is True


def test_user_answered_after_reaction() -> None:
    message = {
        "ts": "1.0",
        "user_id": "U2",
        "text": "<@U1> ping",
        "raw_json": '{"reactions":[{"name":"white_check_mark","users":["U1"]}]}',
    }
    assert user_reacted(message, "U1") is True


def test_dismissed_ask_returns_after_new_mention(tmp_path: Path) -> None:
    dismissed = [AskDismissal("C1", "100.000003", "100.000003", "2026-10-16T08:00:00+00:00")]
    messages = [
        {"ts": "100.000003", "user_id": "U2", "text": "<@U1> old ask", "channel_id": "C1"},
        {
            "ts": "100.000004",
            "user_id": "U2",
            "text": "<@U1> follow-up please",
            "channel_id": "C1",
        },
    ]
    assert is_dismissed(dismissed, "C1", "100.000003", messages[0], messages, "U1") is False


def test_load_dismissed_state_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"dismissed":[{"channel_id":"C1","thread_ts":"1.0","ask_ts":"1.0","dismissed_at":"t"}]}',
        encoding="utf-8",
    )
    [entry] = load_dismissed_state(state_path)
    assert entry.channel_id == "C1"
