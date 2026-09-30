from __future__ import annotations

from collections.abc import Generator, Iterator
from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo

from .cleanup import TextCleaner
from .references import local_minute, slack_href
from .slacrawl import Author, BotStatus, SourceMessage, SourceThread


class OmissionReason(Enum):
    REDACTED = "redacted"
    FILTERED_BOT = "filtered_bot"
    MISSING_FROM_SOURCE = "missing_from_source"


@dataclass(frozen=True)
class PreparedMessage:
    channel_id: str
    ts: str
    thread_ts: str | None
    author: Author
    text: str
    context_only: bool


@dataclass(frozen=True)
class MessageOmitted:
    reason: OmissionReason


@dataclass(frozen=True)
class PreparedThread:
    root_ts: str
    root: PreparedMessage | None
    replies: tuple[PreparedMessage, ...]
    root_omitted_reason: OmissionReason | None


def iter_thread_records(
    source_threads: Generator[SourceThread],
    *,
    cleaner: TextCleaner,
    include_bots: bool,
    limit: int,
    workspace_url: str,
    timezone: ZoneInfo,
) -> Iterator[dict[str, object]]:
    emitted = 0
    try:
        for source_thread in source_threads:
            prepared = prepare_thread(source_thread, cleaner=cleaner, include_bots=include_bots)
            if prepared is None:
                continue
            yield thread_record(prepared, workspace_url, timezone)
            emitted += 1
            if emitted == limit:
                return
    finally:
        source_threads.close()


def prepare_thread(
    source_thread: SourceThread, *, cleaner: TextCleaner, include_bots: bool
) -> PreparedThread | None:
    root: PreparedMessage | None = None
    replies: list[PreparedMessage] = []
    source_root: SourceMessage | None = None
    root_reason: OmissionReason | None = None
    has_in_window_message = False

    for source in source_thread.messages:
        is_root = source.ts == source_thread.root_ts
        if is_root:
            source_root = source
        result = prepare_message(source, cleaner=cleaner, include_bots=include_bots)
        if isinstance(result, MessageOmitted):
            if is_root:
                root_reason = result.reason
            continue
        prepared = result
        if is_root:
            root = PreparedMessage(
                channel_id=prepared.channel_id,
                ts=prepared.ts,
                thread_ts=prepared.thread_ts,
                author=prepared.author,
                text=prepared.text,
                context_only=not source.in_window,
            )
        else:
            replies.append(prepared)
        has_in_window_message = has_in_window_message or (source.in_window and prepared is not None)

    if source_root is None:
        root_reason = OmissionReason.MISSING_FROM_SOURCE
    if not has_in_window_message or (root is None and not replies):
        return None
    return PreparedThread(source_thread.root_ts, root, tuple(replies), root_reason)


def prepare_message(
    source: SourceMessage, *, cleaner: TextCleaner, include_bots: bool
) -> PreparedMessage | MessageOmitted:
    if source.bot_status is BotStatus.BOT and not include_bots:
        return MessageOmitted(OmissionReason.FILTERED_BOT)
    cleaned = cleaner.clean(source.text)
    if cleaned is None:
        return MessageOmitted(OmissionReason.REDACTED)
    return PreparedMessage(
        channel_id=source.channel_id,
        ts=source.ts,
        thread_ts=source.thread_ts,
        author=source.author,
        text=cleaned,
        context_only=False,
    )


def thread_record(
    thread: PreparedThread, workspace_url: str, timezone: ZoneInfo
) -> dict[str, object]:
    channel_id = thread.root.channel_id if thread.root else thread.replies[0].channel_id
    return {
        "thread": {
            "href": slack_href(workspace_url, channel_id, thread.root_ts, None),
            "root": message_record(thread.root, workspace_url, timezone) if thread.root else None,
            "replies": [message_record(reply, workspace_url, timezone) for reply in thread.replies],
            "root_omitted_reason": (
                thread.root_omitted_reason.value if thread.root_omitted_reason else None
            ),
            "coverage": "source_may_be_incomplete",
        }
    }


def message_record(
    message: PreparedMessage, workspace_url: str, timezone: ZoneInfo
) -> dict[str, object]:
    return {
        "channel_id": message.channel_id,
        "timestamp": local_minute(message.ts, timezone),
        "author": {"id": message.author.id, "name": message.author.name},
        "text": message.text,
        "href": slack_href(workspace_url, message.channel_id, message.ts, message.thread_ts),
        "context_only": message.context_only,
    }
