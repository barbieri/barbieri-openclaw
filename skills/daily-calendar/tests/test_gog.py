from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from daily_calendar.gog import (
    GogPermissionError,
    GogRateLimitError,
    classify_gog_failure,
    ensure_gmail_query_excludes_trash,
    load_send_state,
    parse_retry_after_seconds,
    record_digest_send,
    run_gog,
    should_skip_digest_send,
)


def test_ensure_gmail_query_excludes_trash_appends_filter() -> None:
    assert ensure_gmail_query_excludes_trash("is:unread") == "is:unread -in:trash"


def test_ensure_gmail_query_rejects_trash_reads() -> None:
    with pytest.raises(ValueError, match="must not read Gmail Trash"):
        ensure_gmail_query_excludes_trash("in:trash newer_than:1d")


def test_classify_rate_limit_403_is_retryable() -> None:
    failure = classify_gog_failure(
        403,
        stdout="",
        stderr='{"error":{"errors":[{"reason":"rateLimitExceeded"}]}}',
    )
    assert isinstance(failure, GogRateLimitError)


def test_classify_permission_403_is_not_retryable() -> None:
    failure = classify_gog_failure(
        403,
        stdout="",
        stderr='{"error":{"errors":[{"reason":"forbidden"}]}} insufficient permission',
    )
    assert isinstance(failure, GogPermissionError)


def test_parse_retry_after_seconds() -> None:
    assert parse_retry_after_seconds("Retry-After: 12") == 12


def test_run_gog_retries_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                ["gog"],
                429,
                stdout="",
                stderr="rateLimitExceeded",
            )
        return subprocess.CompletedProcess(["gog"], 0, stdout='{"events":[]}', stderr="")

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    monkeypatch.setattr("daily_calendar.gog.time.sleep", lambda _seconds: None)

    result = run_gog(["gog", "calendar", "events", "primary"], max_attempts=3)
    assert result.returncode == 0
    assert calls["count"] == 2


def test_send_guard_skips_repeat_digest() -> None:
    sends = {"2026-10-16": "2026-10-16T08:00:00+00:00"}
    assert should_skip_digest_send(sends, "2026-10-16", force=False) is True
    assert should_skip_digest_send(sends, "2026-10-16", force=True) is False


def test_record_digest_send_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "send-state.json"
    record_digest_send(str(state_path), "2026-10-16", "2026-10-16T08:00:00+00:00")
    assert load_send_state(str(state_path))["2026-10-16"] == "2026-10-16T08:00:00+00:00"
