from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from daily_calendar.gog import (
    GogPermissionError,
    GogRateLimitError,
    GogTransientError,
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


def test_classify_googleapi_503_is_retryable_but_403_is_not() -> None:
    unavailable = classify_gog_failure(1, "", "googleapi: Error 503: backendError")
    denied = classify_gog_failure(1, "", "googleapi: Error 403: service unavailable")

    assert isinstance(unavailable, GogTransientError)
    assert unavailable.http_status == 503
    assert isinstance(denied, subprocess.CalledProcessError)
    assert not isinstance(denied, GogTransientError)


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

    result = run_gog(["gog", "calendar", "events", "primary"], max_attempts=3, retry_safe=True)
    assert result.returncode == 0
    assert calls["count"] == 2


def test_run_gog_retries_transient_server_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                ["gog"], 1, stdout="private event text", stderr="googleapi: Error 503: backendError"
            )
        return subprocess.CompletedProcess(["gog"], 0, stdout='{"events":[]}', stderr="")

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    monkeypatch.setattr("daily_calendar.gog.time.sleep", lambda _seconds: None)
    assert (
        run_gog(
            ["gog", "calendar", "events"], operation="calendar events", retry_safe=True
        ).returncode
        == 0
    )
    assert calls["count"] == 2


def test_run_gog_retries_timeouts_and_reports_safe_context(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise subprocess.TimeoutExpired(["gog", "private query"], timeout=60, stderr="private")
        return subprocess.CompletedProcess(["gog"], 0, stdout="ok", stderr="")

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    monkeypatch.setattr("daily_calendar.gog.time.sleep", lambda _seconds: None)
    result = run_gog(["gog", "calendar", "events"], operation="calendar events", retry_safe=True)
    assert result.stdout == "ok"
    assert calls["count"] == 2


def test_run_gog_does_not_retry_non_idempotent_send(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        raise subprocess.TimeoutExpired(["gog", "gmail", "send"], timeout=60)

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    with pytest.raises(GogTransientError, match=r"gmail send failed \(1 attempts, timeout\)"):
        run_gog(["gog", "gmail", "send"], operation="gmail send", retry_safe=False)
    assert calls["count"] == 1


def test_run_gog_does_not_retry_permission_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        return subprocess.CompletedProcess(
            ["gog"], 403, stdout="private", stderr="insufficient permission"
        )

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    with pytest.raises(GogPermissionError):
        run_gog(["gog", "calendar", "events"], operation="calendar events")
    assert calls["count"] == 1


def test_run_gog_reports_bounded_retry_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        raise subprocess.TimeoutExpired(["gog", "private"], timeout=60, stderr="private")

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    monkeypatch.setattr("daily_calendar.gog.time.sleep", lambda _seconds: None)
    with pytest.raises(GogTransientError, match=r"calendar events failed \(3 attempts, timeout\)"):
        run_gog(["gog", "calendar", "events"], operation="calendar events", retry_safe=True)
    assert calls["count"] == 3


def test_run_gog_defaults_to_no_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        return subprocess.CompletedProcess(
            ["gog"], 1, stdout="", stderr="HTTP 503 service unavailable"
        )

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    with pytest.raises(GogTransientError) as captured:
        run_gog(["gog", "gmail", "send"])
    assert calls["count"] == 1
    assert captured.value.exit_code == 1
    assert captured.value.http_status == 503


def test_run_gog_does_not_retry_local_launch_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        raise FileNotFoundError("private path")

    monkeypatch.setattr("daily_calendar.gog.subprocess.run", fake_run)
    from daily_calendar.gog import GogExecutionError

    with pytest.raises(GogExecutionError, match="local execution error"):
        run_gog(["gog", "calendar", "events"], retry_safe=True)
    assert calls["count"] == 1


def test_classified_errors_do_not_retain_provider_output() -> None:
    failure = classify_gog_failure(403, "private response", "insufficient permission")
    assert isinstance(failure, GogPermissionError)
    assert failure.stdout == ""
    assert failure.stderr == ""


def test_send_guard_skips_repeat_digest() -> None:
    sends = {"2026-10-16": "2026-10-16T08:00:00+00:00"}
    assert should_skip_digest_send(sends, "2026-10-16", force=False) is True
    assert should_skip_digest_send(sends, "2026-10-16", force=True) is False


def test_record_digest_send_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "send-state.json"
    record_digest_send(str(state_path), "2026-10-16", "2026-10-16T08:00:00+00:00")
    assert load_send_state(str(state_path))["2026-10-16"] == "2026-10-16T08:00:00+00:00"
