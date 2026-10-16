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
        super().__init__(returncode, [], output=stdout, stderr=stderr)


class GogPermissionError(subprocess.CalledProcessError):
    """gog failed with a non-retryable permission error."""

    def __init__(self, returncode: int, *, stdout: str, stderr: str) -> None:
        super().__init__(returncode, [], output=stdout, stderr=stderr)


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
) -> subprocess.CalledProcessError | None:
    combined = f"{stdout}\n{stderr}".casefold()
    if returncode == 429 or _looks_like_rate_limit(combined):
        return GogRateLimitError(returncode, stderr=stderr, stdout=stdout)
    if returncode == 403 and _looks_like_rate_limit(combined):
        return GogRateLimitError(returncode, stderr=stderr, stdout=stdout)
    if returncode == 403 or _looks_like_permission_denied(combined):
        return GogPermissionError(returncode, stderr=stderr, stdout=stdout)
    if returncode != 0:
        return subprocess.CalledProcessError(returncode, [], output=stdout, stderr=stderr)
    return None


def run_gog(
    command: Sequence[str],
    *,
    max_attempts: int = 5,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(max_attempts):
        result = subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            text=True,
        )
        failure = classify_gog_failure(result.returncode, result.stdout, result.stderr)
        if failure is None:
            return result

        if not isinstance(failure, GogRateLimitError) or attempt == max_attempts - 1:
            raise failure

        delay = min(
            max_delay_seconds,
            base_delay_seconds * (2**attempt) + random.uniform(0, 0.5),
        )
        retry_after = parse_retry_after_seconds(f"{result.stdout}\n{result.stderr}")
        if retry_after is not None:
            delay = max(delay, float(retry_after))
        time.sleep(delay)
        last_error = failure

    if last_error is not None:
        raise last_error
    raise RuntimeError("run_gog finished without a result")


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
