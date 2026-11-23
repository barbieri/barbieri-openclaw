from __future__ import annotations

import json
import random
import re
import subprocess
import time
from collections.abc import Sequence

RATE_LIMIT_MARKERS = (
    "ratelimitexceeded",
    "userratelimitexceeded",
    "quota exceeded",
    "rate limit",
)
PERMISSION_MARKERS = (
    "insufficient permission",
    "insufficientpermissions",
    "access not configured",
    "forbidden",
    "not authorized",
)
RETRY_AFTER_RE = re.compile(r"retry[- ]after[:\s]+(\d+)", re.IGNORECASE)
TRANSIENT_MARKERS = (
    "internal server error",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "connection reset",
    "connection refused",
    "temporarily unavailable",
    "deadline exceeded",
)

CALENDAR_EVENT_FIELDS = ",".join(
    (
        "id",
        "iCalUID",
        "summary",
        "start",
        "end",
        "location",
        "description",
        "hangoutLink",
        "conferenceData",
        "eventType",
        "recurringEventId",
        "attendees",
        "organizer",
        "creator",
        "transparency",
    )
)

GMAIL_TRASH_QUERY = "-in:trash"


class GogRateLimitError(subprocess.CalledProcessError):
    """gog failed with a retryable Google rate limit."""

    def __init__(self, returncode: int, *, stdout: str, stderr: str) -> None:
        super().__init__(returncode, [], output="", stderr="")
        self.operation = "request"
        self.attempts = 1
        self.http_status: int | None = None


class GogPermissionError(subprocess.CalledProcessError):
    """gog failed with a non-retryable permission error."""

    def __init__(self, returncode: int, *, stdout: str, stderr: str) -> None:
        super().__init__(returncode, [], output="", stderr="")
        self.operation = "request"
        self.http_status: int | None = None


class GogTransientError(RuntimeError):
    """A read failed after bounded retries; fields contain no provider payload."""

    def __init__(
        self,
        operation: str,
        category: str,
        attempts: int,
        http_status: int | None = None,
        exit_code: int | None = None,
    ) -> None:
        details = [f"{attempts} attempts", category]
        if exit_code is not None:
            details.append(f"exit code {exit_code}")
        if http_status is not None:
            details.append(f"HTTP {http_status}")
        super().__init__(f"gog {operation} failed ({', '.join(details)})")
        self.operation = operation
        self.category = category
        self.attempts = attempts
        self.http_status = http_status
        self.exit_code = exit_code


class GogExecutionError(RuntimeError):
    """A local gog launch failure, with no retry or command payload."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"gog {operation} could not be started (local execution error)")
        self.operation = operation
        self.category = "local_execution_error"


def ensure_gmail_query_excludes_trash(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        return GMAIL_TRASH_QUERY
    if "in:trash" in normalized.casefold():
        raise ValueError("gmail queries must not read Gmail Trash")
    if GMAIL_TRASH_QUERY in normalized:
        return normalized
    return f"{normalized} {GMAIL_TRASH_QUERY}"


def classify_gog_failure(
    returncode: int, stdout: str, stderr: str
) -> subprocess.CalledProcessError | GogTransientError | None:
    combined = stderr.casefold()
    if returncode == 429 or _looks_like_rate_limit(combined):
        failure = GogRateLimitError(returncode, stderr=stderr, stdout=stdout)
        failure.http_status = _http_status_from_text(stderr) or (
            returncode if returncode in range(400, 600) else None
        )
        return failure
    if returncode == 403 and _looks_like_rate_limit(combined):
        return GogRateLimitError(returncode, stderr=stderr, stdout=stdout)
    if returncode == 403 or _looks_like_permission_denied(combined):
        failure = GogPermissionError(returncode, stderr=stderr, stdout=stdout)
        failure.http_status = _http_status_from_text(stderr) or (
            returncode if returncode in range(400, 600) else None
        )
        return failure
    if _looks_like_transient(stderr.casefold()):
        return GogTransientError(
            "request", "server_error", 1, _http_status_from_text(stderr), returncode
        )
    if returncode != 0:
        failure = subprocess.CalledProcessError(returncode, [], output="", stderr="")
        failure.http_status = _http_status_from_text(stderr)
        return failure
    return None


def run_gog(
    command: Sequence[str],
    *,
    operation: str = "request",
    retry_safe: bool = False,
    timeout_seconds: int = 60,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                list(command),
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            if not retry_safe or attempt == max_attempts - 1:
                raise GogTransientError(operation, "timeout", attempt + 1) from None
            _sleep_before_retry(attempt, base_delay_seconds, max_delay_seconds)
            continue
        except OSError:
            raise GogExecutionError(operation) from None
        failure = classify_gog_failure(result.returncode, result.stdout, result.stderr)
        if failure is None:
            return result

        transient = isinstance(failure, (GogRateLimitError, GogTransientError))
        if not transient or not retry_safe or attempt == max_attempts - 1:
            if isinstance(failure, GogTransientError):
                raise GogTransientError(
                    operation, failure.category, attempt + 1, failure.http_status, result.returncode
                ) from None
            if isinstance(failure, GogRateLimitError):
                failure.operation = operation
                failure.attempts = attempt + 1
                failure.http_status = _http_status_from_text(result.stderr)
            elif isinstance(failure, GogPermissionError):
                failure.operation = operation
            else:
                failure.operation = operation
            raise failure
        if isinstance(failure, GogRateLimitError):
            retry_after = parse_retry_after_seconds(f"{result.stdout}\n{result.stderr}")
        else:
            retry_after = None
        _sleep_before_retry(attempt, base_delay_seconds, max_delay_seconds, retry_after)
        last_error = failure

    if last_error is not None:
        raise last_error
    raise RuntimeError("run_gog finished without a result")


def _sleep_before_retry(
    attempt: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
    retry_after: int | None = None,
) -> None:
    delay = min(max_delay_seconds, base_delay_seconds * (2**attempt) + random.uniform(0, 0.5))
    if retry_after is not None:
        delay = min(max_delay_seconds, max(delay, float(retry_after)))
    time.sleep(delay)


def _looks_like_transient(stderr: str) -> bool:
    http_status = _http_status_from_text(stderr)
    if http_status is not None:
        return http_status >= 500
    return bool(
        re.search(r"(?:http(?:/\d(?:\.\d)?)?\s+|status(?:\s+code)?[:= ]+)(5\d\d)", stderr)
    ) or any(marker in stderr for marker in TRANSIENT_MARKERS)


def parse_retry_after_seconds(text: str) -> int | None:
    match = RETRY_AFTER_RE.search(text)
    if not match:
        return None
    try:
        return max(0, int(match.group(1)))
    except ValueError:
        return None


def _looks_like_rate_limit(combined: str) -> bool:
    return any(marker in combined for marker in RATE_LIMIT_MARKERS)


def _looks_like_permission_denied(combined: str) -> bool:
    if _looks_like_rate_limit(combined):
        return False
    return any(marker in combined for marker in PERMISSION_MARKERS)


def load_send_state(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    from pathlib import Path

    state_path = Path(path)
    if not state_path.exists():
        return {}
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("send state file must be a JSON object")
    sends = data.get("sends", {})
    if not isinstance(sends, dict):
        raise ValueError("send state file sends must be an object")
    return {str(key): str(value) for key, value in sends.items()}


def should_skip_digest_send(sends: dict[str, str], report_day: str, *, force: bool) -> bool:
    if force:
        return False
    return report_day in sends


def record_digest_send(path: str, report_day: str, sent_at: str) -> None:
    from pathlib import Path

    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    sends = load_send_state(str(state_path))
    sends[report_day] = sent_at
    state_path.write_text(
        json.dumps({"sends": sends}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _http_status_from_text(text: str) -> int | None:
    match = re.search(
        r"(?:http(?:/\d(?:\.\d)?)?\s+|status(?:\s+code)?[:= ]+|googleapi:\s*error\s+)([45]\d\d)\b",
        text,
        re.I,
    )
    return int(match.group(1)) if match else None
