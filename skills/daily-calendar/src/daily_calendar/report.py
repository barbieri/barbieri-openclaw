from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from daily_calendar.email import compose_report_markdown
from daily_calendar.email import markdown_to_html as markdown_to_html
from daily_calendar.email import strip_chat_instructions as strip_chat_instructions
from daily_calendar.windowing import effective_report_day_count

STATUS_ICONS = {
    "accepted": "",
    "tentative": "❓",
    "needsAction": "⏳",
}

URL_RE = re.compile(r"https?://[^\s<>\[\]\)]+")
VIRTUAL_LOCATION_RE = re.compile(
    r"\b(?:microsoft\s+teams|teams|google\s+meet|zoom|webex)\s+(?:meeting|call)\b",
    re.IGNORECASE,
)
PHYSICAL_ADDRESS_RE = re.compile(
    r"\b(?:"
    r"rua|avenida|av\.?|alameda|travessa|pra[cç]a|"
    r"street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|blvd\.?"
    r")\b",
    re.IGNORECASE,
)
STREET_NUMBER_RE = re.compile(r"(?:^|[,\s])(?:n[ºo°.]?\s*)?\d{1,5}(?:\s*[-/]\s*\d+)?(?:\s|,|$)")
POSTAL_CODE_RE = re.compile(r"\b\d{5}-?\d{3}\b")
ROOM_ONLY_RE = re.compile(
    r"^(?:room|sala|audit[oó]rio|conference room|meeting room)\b",
    re.IGNORECASE,
)
HOLIDAY_SUMMARY_RE = re.compile(r"\b(?:holiday|feriado|public holiday)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CalendarSource:
    account: str
    label: str


@dataclass(frozen=True)
class CalendarReport:
    body: str
    footer: str | None = None


@dataclass(frozen=True)
class ReportEvent:
    start: datetime
    all_day: bool
    summary: str
    display_summary: str
    calendars: tuple[str, ...]
    recurring: bool
    status_icon: str
    type_icons: tuple[str, ...]
    end: datetime | None
    overlapping: bool = False
    tight: bool = False


def parse_datetime(value: str | None, timezone: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone)
    return parsed.replace(tzinfo=timezone)


def event_end(event: dict, timezone: ZoneInfo) -> datetime | None:
    end = event.get("end", {})
    if not isinstance(end, dict):
        return None

    date_value = end.get("date")
    if isinstance(date_value, str):
        if end.get("dateTime") is not None:
            return None
        if end.get("endLocal") is not None and end.get("endLocal") != date_value:
            return None
        try:
            parsed_date = date.fromisoformat(date_value)
        except ValueError:
            return None
        if date_value != parsed_date.isoformat():
            return None
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone)

    end_datetime = end.get("dateTime")
    if isinstance(end_datetime, str):
        if "T" not in end_datetime:
            return None
        return parse_datetime(end_datetime, timezone)

    end_local = end.get("endLocal")
    if isinstance(end_local, str):
        if "T" not in end_local:
            return None
        return parse_datetime(end_local, timezone)

    return None


def format_time(value: datetime | None) -> str:
    if not value:
        return "All day"
    return value.strftime("%H:%M")


def _format_duration(start: datetime, end: datetime | None) -> str:
    if end is None or end <= start:
        return ""

    total_minutes = int((end - start).total_seconds() // 60)
    if total_minutes <= 0:
        return ""

    hours, minutes = divmod(total_minutes, 60)
    text = ""
    if hours:
        text += f"{hours}h"
    if minutes:
        text += f"{minutes}m"
    return text


def _format_time_cell(event: ReportEvent) -> str:
    if event.all_day:
        return "All day"

    base = format_time(event.start)
    duration = _format_duration(event.start, event.end)
    if not duration:
        return base

    return f"{base} ({duration})"


def format_date(value: datetime) -> str:
    return value.strftime("%d/%m (%A)")


def event_start(event: dict, timezone: ZoneInfo) -> tuple[datetime | None, bool]:
    value, all_day = event_start_value(event)
    if all_day:
        value = f"{value}T00:00:00"
    return parse_datetime(value, timezone), all_day


def event_start_value(event: dict) -> tuple[str, bool]:
    start = event.get("start", {})
    if not isinstance(start, dict):
        raise ValueError("calendar response event 'start' must be an object")

    date_value = start.get("date")
    datetime_value = start.get("dateTime")
    local_value = event.get("startLocal")
    for field, value in (
        ("start.date", date_value),
        ("start.dateTime", datetime_value),
        ("startLocal", local_value),
    ):
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"calendar response event {field} must be a non-empty string")

    if date_value is not None:
        if datetime_value is not None:
            raise ValueError("calendar response event start fields are contradictory")
        try:
            parsed_date = date.fromisoformat(date_value)
        except ValueError as exc:
            raise ValueError("calendar response event start.date is invalid") from exc
        if date_value != parsed_date.isoformat():
            raise ValueError("calendar response event start.date must use YYYY-MM-DD")
        if local_value is not None and local_value != date_value:
            raise ValueError("calendar response event start fields are contradictory")
        return date_value, True

    for field, value in (("start.dateTime", datetime_value), ("startLocal", local_value)):
        if value is None:
            continue
        if "T" not in value:
            raise ValueError(f"calendar response event {field} must include a time")
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"calendar response event {field} is invalid") from exc

    if datetime_value is not None:
        return datetime_value, False
    if local_value is not None:
        return local_value, False
    raise ValueError("calendar response event must contain a start date or datetime")


def markdown_cell(value: object, limit: int | None = None) -> str:
    text = " ".join(str(value).splitlines())
    if limit is not None:
        text = text[:limit]
    return text.replace("|", r"\|")


def _event_has_online_link(event: dict) -> bool:
    for key in ("hangoutLink", "location", "description"):
        value = event.get(key)
        if isinstance(value, str) and (URL_RE.search(value) or VIRTUAL_LOCATION_RE.search(value)):
            return True

    conference_data = event.get("conferenceData")
    if isinstance(conference_data, dict):
        if conference_data.get("conferenceId"):
            return True
        entry_points = conference_data.get("entryPoints", [])
        if isinstance(entry_points, list) and entry_points:
            return True
        if isinstance(entry_points, dict):
            return True
        for value in (
            conference_data.get("conferenceSolution"),
            conference_data.get("signature"),
            conference_data.get("externalUri"),
        ):
            if isinstance(value, str) and URL_RE.search(value):
                return True
    return False


def _location_text(event: dict) -> str | None:
    location = event.get("location")
    if not isinstance(location, str):
        return None
    stripped = location.strip()
    return stripped or None


def _looks_like_physical_address(location: str) -> bool:
    if URL_RE.search(location) or VIRTUAL_LOCATION_RE.search(location):
        return False
    if ROOM_ONLY_RE.search(location.strip()):
        return False
    if PHYSICAL_ADDRESS_RE.search(location):
        return True
    if POSTAL_CODE_RE.search(location):
        return True
    return bool(STREET_NUMBER_RE.search(location))


def _extract_city(location: str) -> str | None:
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if len(parts) < 2:
        return None
    for part in reversed(parts):
        if POSTAL_CODE_RE.search(part):
            continue
        if re.fullmatch(r"[A-Z]{2}", part.strip(), flags=re.IGNORECASE):
            continue
        if re.search(r"\d", part):
            continue
        if len(part) >= 3:
            return part
    return None


def _physical_location_note(event: dict) -> str | None:
    location = _location_text(event)
    if location is None or not _looks_like_physical_address(location):
        return None
    city = _extract_city(location)
    return city


def _event_is_in_person(event: dict) -> bool:
    location = _location_text(event)
    if location is None:
        return False
    return _looks_like_physical_address(location)


def _format_event_summary(event: dict) -> str:
    summary = event.get("summary", "Untitled")
    city = _physical_location_note(event)
    if city:
        return f"{summary} · {city}"
    return summary


def _event_type_icons(event: dict) -> tuple[str, ...]:
    icons: list[str] = []
    if _event_has_online_link(event):
        icons.append("💻")
    if _event_is_in_person(event):
        icons.append("📍")
    if len(event.get("attendees", [])) > 3:
        icons.append("👥")
    return tuple(icons)


def _build_status_cell(event: ReportEvent) -> str:
    status_parts: list[str] = [event.status_icon]
    if event.recurring:
        status_parts.append("🔁")
    status_parts.extend(event.type_icons)
    if event.overlapping:
        status_parts.append("⚠️")
    if event.tight:
        status_parts.append("🥵")
    return " ".join(part for part in status_parts if part)


def get_response_status(event: dict) -> tuple[str | None, str]:
    for attendee in event.get("attendees", []):
        if attendee.get("self", False):
            status = attendee.get("responseStatus", "needsAction")
            return status, STATUS_ICONS.get(status, "")

    organizer = event.get("organizer", {})
    creator = event.get("creator", {})
    if organizer.get("self") or creator.get("self"):
        return "accepted", STATUS_ICONS["accepted"]

    return None, ""


def should_skip_event(event: dict) -> bool:
    event_type = event.get("eventType")
    if event_type in {"birthday", "focusTime", "workingLocation", "outOfOffice"}:
        return True

    summary = event.get("summary")
    if isinstance(summary, str) and HOLIDAY_SUMMARY_RE.search(summary):
        start = event.get("start", {})
        if isinstance(start, dict) and start.get("date") and not start.get("dateTime"):
            return True

    availability = event.get("transparency")
    if isinstance(availability, str) and availability.lower() in {"transparent", "free"}:
        return True

    availability = event.get("showAs")
    if isinstance(availability, str) and availability.lower() == "free":
        return True

    availability = event.get("availability")
    if isinstance(availability, str) and availability.lower() == "free":
        return True

    status, _ = get_response_status(event)
    return status == "declined"


def collect_events(
    events_by_account: dict[str, dict],
    sources: list[CalendarSource],
    timezone: ZoneInfo,
) -> list[ReportEvent]:
    events_by_key: dict[tuple[str, ...], ReportEvent] = {}

    for source in sources:
        data = events_by_account.get(source.account, {})
        for event_index, event in enumerate(data.get("events", [])):
            if should_skip_event(event):
                continue

            start, all_day = event_start(event, timezone)
            if not start:
                continue

            if event_uid := event.get("iCalUID"):
                key = ("ical", str(event_uid), start.isoformat())
            elif event_id := event.get("id"):
                key = ("account", source.account, str(event_id))
            else:
                key = ("anonymous", source.account, str(event_index))

            if existing := events_by_key.get(key):
                if source.label not in existing.calendars:
                    events_by_key[key] = replace(
                        existing,
                        calendars=(*existing.calendars, source.label),
                    )
                continue

            _, status_icon = get_response_status(event)
            display_summary = _format_event_summary(event)
            events_by_key[key] = ReportEvent(
                start=start,
                all_day=all_day,
                summary=event.get("summary", "Untitled"),
                display_summary=display_summary,
                calendars=(source.label,),
                recurring="recurringEventId" in event,
                status_icon=status_icon,
                type_icons=_event_type_icons(event),
                end=event_end(event, timezone),
            )

    return sorted(events_by_key.values(), key=lambda event: (event.start, event.summary.casefold()))


def _mark_overlapping_events(events: list[ReportEvent]) -> list[ReportEvent]:
    if len(events) <= 1:
        return events

    overlapping_by_index = [False] * len(events)

    for i, current in enumerate(events):
        if current.end is None:
            continue
        for j in range(i + 1, len(events)):
            other = events[j]
            if other.start >= current.end:
                break
            if other.end is None:
                continue
            if other.start < current.end:
                overlapping_by_index[i] = True
                overlapping_by_index[j] = True

    if not any(overlapping_by_index):
        return events

    return [
        replace(event, overlapping=overlapping)
        for event, overlapping in zip(events, overlapping_by_index, strict=True)
    ]


def _mark_tight_transitions(events: list[ReportEvent]) -> list[ReportEvent]:
    if len(events) <= 1:
        return events

    tight_by_index = [False] * len(events)
    for idx, event in enumerate(events):
        if idx == 0:
            continue

        previous = events[idx - 1]
        if previous.all_day or event.all_day or previous.end is None:
            continue

        gap = event.start - previous.end
        if timedelta(0) <= gap < timedelta(minutes=5):
            tight_by_index[idx] = True

    if not any(tight_by_index):
        return events

    return [
        replace(event, tight=tight) for event, tight in zip(events, tight_by_index, strict=True)
    ]


def build_report_markdown(
    events_by_account: dict[str, dict],
    sources: list[CalendarSource],
    *,
    now: datetime,
    timezone: ZoneInfo,
    calendar_days: int = 2,
    include_chat_instructions: bool = False,
    compact: bool = False,
) -> str:
    report = build_calendar_report(
        events_by_account,
        sources,
        now=now,
        timezone=timezone,
        calendar_days=calendar_days,
        include_chat_instructions=include_chat_instructions,
        compact=compact,
    )
    return compose_report_markdown(report.body, "", footer=report.footer)


def build_calendar_report(
    events_by_account: dict[str, dict],
    sources: list[CalendarSource],
    *,
    now: datetime,
    timezone: ZoneInfo,
    calendar_days: int = 2,
    include_chat_instructions: bool = False,
    compact: bool = False,
) -> CalendarReport:
    today = now.astimezone(timezone).replace(hour=0, minute=0, second=0, microsecond=0)

    lines: list[str] = []
    report_day_count = effective_report_day_count(today.date(), calendar_days)
    report_dates = [(today + timedelta(days=offset)).date() for offset in range(report_day_count)]
    events = collect_events(events_by_account, sources, timezone)

    lines.append("# Daily Calendar Report")
    lines.append("")
    generated_at = f"_Generated at: {now.astimezone(timezone).strftime('%d/%m/%Y %H:%M')}_"
    if not compact:
        lines.append(generated_at)
        lines.append("")
        lines.append("---")
        lines.append("")

    for report_date in report_dates:
        daily_events = [event for event in events if event.start.date() == report_date]
        daily_events = _mark_overlapping_events(daily_events)
        daily_events = _mark_tight_transitions(daily_events)
        date_display = datetime.combine(report_date, datetime.min.time(), tzinfo=timezone)

        lines.append(f"## {format_date(date_display)}")
        lines.append("")

        if not daily_events:
            lines.append("No events scheduled for this day.")
            lines.append("")
            if not compact:
                lines.extend(["---", ""])
            continue

        lines.append("| Time | Event | Calendar | Status |")
        lines.append("|------|-------|----------|--------|")
        for event in daily_events:
            lines.append(
                "| "
                f"{_format_time_cell(event)} | "
                f"{markdown_cell(event.display_summary)} | "
                f"{markdown_cell(', '.join(event.calendars))} | "
                f"{_build_status_cell(event)} |"
            )

        lines.append("")
        if not compact:
            lines.extend(["---", ""])

    if include_chat_instructions:
        lines.append("**How to use event numbers:**")
        lines.append('- Cancel: "Cancel event #1"')
        lines.append('- Reschedule: "Reschedule event #2 to 10/09 at 14:00"')
        lines.append("")

    if not compact:
        lines.append("**Legend:**")
        lines.append("- ⚠️ = Overlapping events / Conflict")
        lines.append("- 🥵 = Back-to-back / tight transition <5m")
        lines.append("- ❓ = Tentative / Maybe")
        lines.append("- ⏳ = Needs response")
        lines.append("- 🔁 = Recurring event")
        lines.append("- 💻 = Online meeting")
        lines.append("- 📍 = In-person / physical address")
        lines.append("- 👥 = More than 3 invitees")
        lines.append("")
    lines.append("_Declined, free, holiday, and birthday events are omitted automatically._")
    lines.append("")

    return CalendarReport("\n".join(lines), generated_at if compact else None)
