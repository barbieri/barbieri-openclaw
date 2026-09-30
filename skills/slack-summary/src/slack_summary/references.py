from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo


def normalize_workspace_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--workspace-url must be an HTTP(S) URL with a host")
    has_disallowed_part = bool(
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    )
    if has_disallowed_part:
        raise ValueError(
            "--workspace-url must be an origin without credentials, path, query, or fragment"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def slack_href(workspace_url: str, channel_id: str, ts: str, thread_ts: str | None) -> str:
    message_url = (
        f"{normalize_workspace_url(workspace_url)}/archives/{channel_id}/p{ts.replace('.', '')}"
    )
    if not thread_ts or thread_ts == ts:
        return message_url
    return f"{message_url}?{urlencode({'thread_ts': thread_ts})}"


def local_minute(ts: str, timezone: ZoneInfo) -> str:
    instant = datetime.fromtimestamp(float(ts), tz=UTC).astimezone(timezone)
    return instant.replace(second=0, microsecond=0).isoformat(timespec="minutes")
