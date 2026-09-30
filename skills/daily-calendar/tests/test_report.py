from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from daily_calendar.report import CalendarSource, build_report_markdown, markdown_to_html


def test_email_html_renders_tables_and_removes_chat_instructions() -> None:
    markdown = """# Daily Calendar Report

| Time | Event |
|------|-------|
| 09:00 | Planning |

**How to use event numbers:**
- Cancel: "Cancel event #1"

**Legend:**
- ❓ = Tentative / Maybe
"""

    html = markdown_to_html(markdown)

    assert "<table" in html
    assert "<h1>Daily Calendar Report</h1>" in html
    assert "How to use event numbers" not in html
    assert "Cancel event #1" not in html
    assert "<li>❓ = Tentative / Maybe</li>" in html
    assert "[yes]" not in html


def test_report_marks_tentative_and_recurring_with_emojis_and_no_accepted_marker() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "accepted",
                    "summary": "Accepted weekly meeting",
                    "start": {"dateTime": "2026-08-18T09:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                    "recurringEventId": "accepted",
                },
                {
                    "id": "tentative",
                    "summary": "Tentative stand-up",
                    "start": {"dateTime": "2026-08-18T10:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "tentative"}],
                },
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 09:00 | Accepted weekly meeting | Work | 🔁 |" in report
    assert "| 10:00 | Tentative stand-up | Work | ❓ |" in report
    assert "[yes]" not in report


def test_report_marks_overlapping_events_with_warning_indicator() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "meeting-a",
                    "summary": "Deep-dive",
                    "start": {"dateTime": "2026-08-18T10:30:00+00:00"},
                    "end": {"dateTime": "2026-08-18T12:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "meeting-b",
                    "summary": "Client call",
                    "start": {"dateTime": "2026-08-18T11:45:00+00:00"},
                    "end": {"dateTime": "2026-08-18T12:45:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "meeting-c",
                    "summary": "Status recap",
                    "start": {"dateTime": "2026-08-18T13:00:00+00:00"},
                    "end": {"dateTime": "2026-08-18T14:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 10:30 (1h30m) | Deep-dive | Work | ⚠️ |" in report
    assert "| 11:45 (1h) | Client call | Work | ⚠️ |" in report
    assert "| 13:00 (1h) | Status recap | Work |  |" in report
    assert "⚠️ = Overlapping events / Conflict" in report


def test_report_does_not_mark_non_overlapping_events_with_warning_indicator() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "meeting-a",
                    "summary": "Back-to-back A",
                    "start": {"dateTime": "2026-08-18T09:00:00+00:00"},
                    "end": {"dateTime": "2026-08-18T10:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "meeting-b",
                    "summary": "Back-to-back B",
                    "start": {"dateTime": "2026-08-18T10:00:00+00:00"},
                    "end": {"dateTime": "2026-08-18T11:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 09:00 (1h) | Back-to-back A | Work |  |" in report
    assert "| 10:00 (1h) | Back-to-back B | Work | 🥵 |" in report
    overlap_lines = [line for line in report.splitlines() if "Back-to-back" in line]
    assert all("⚠️" not in line for line in overlap_lines)


def test_report_time_column_includes_timed_event_duration() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "quick",
                    "summary": "Quick sync",
                    "start": {"dateTime": "2026-08-18T11:30:00+00:00"},
                    "end": {"dateTime": "2026-08-18T11:45:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "one-hour",
                    "summary": "Deep work",
                    "start": {"dateTime": "2026-08-18T12:00:00+00:00"},
                    "end": {"dateTime": "2026-08-18T13:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "ninety",
                    "summary": "Planning block",
                    "start": {"dateTime": "2026-08-18T14:00:00+00:00"},
                    "end": {"dateTime": "2026-08-18T15:30:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 11:30 (15m) | Quick sync | Work |  |" in report
    assert "| 12:00 (1h) | Deep work | Work |  |" in report
    assert "| 14:00 (1h30m) | Planning block | Work |  |" in report


def test_report_marks_tight_transitions_with_hot_status() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "first",
                    "summary": "Daily kickoff",
                    "start": {"dateTime": "2026-08-18T09:00:00+00:00"},
                    "end": {"dateTime": "2026-08-18T10:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "second",
                    "summary": "Handoff call",
                    "start": {"dateTime": "2026-08-18T10:00:00+00:00"},
                    "end": {"dateTime": "2026-08-18T10:20:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "third",
                    "summary": "Focus block",
                    "start": {"dateTime": "2026-08-18T10:25:00+00:00"},
                    "end": {"dateTime": "2026-08-18T10:55:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "fourth",
                    "summary": "Planning",
                    "start": {"dateTime": "2026-08-18T10:58:00+00:00"},
                    "end": {"dateTime": "2026-08-18T11:18:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 09:00 (1h) | Daily kickoff | Work |  |" in report
    assert "| 10:00 (20m) | Handoff call | Work | 🥵 |" in report
    assert "| 10:25 (30m) | Focus block | Work |  |" in report
    assert "| 10:58 (20m) | Planning | Work | 🥵 |" in report
    assert "🥵 = Back-to-back / tight transition <5m" in report


def test_report_marks_online_meeting_when_links_are_present() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "online",
                    "summary": "Team sync",
                    "start": {"dateTime": "2026-08-18T11:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                    "conferenceData": {
                        "entryPoints": [{"entryPointType": "video"}],
                    },
                }
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 11:00 | Team sync | Work | 💻 |" in report


def test_report_marks_physical_location_and_large_meeting() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "onsite",
                    "summary": "Planning on-site",
                    "start": {"dateTime": "2026-08-18T12:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}]
                    + [{"responseStatus": "accepted"} for _ in range(4)],
                    "location": "Rua das Flores, 123",
                }
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 12:00 | Planning on-site | Work | 📍 👥 |" in report


def test_report_does_not_mark_teams_location_as_in_person() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "teams",
                    "summary": "Feedback ProFUSION Team",
                    "start": {"dateTime": "2026-08-18T12:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                    "location": "Microsoft Teams Meeting",
                }
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 12:00 | Feedback ProFUSION Team | Work | 💻 |" in report


def test_report_omits_declined_events_and_birthdays() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "accepted",
                    "iCalUID": "accepted",
                    "summary": "Accepted meeting",
                    "start": {"dateTime": "2026-08-18T09:00:00-03:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "declined",
                    "iCalUID": "declined",
                    "summary": "Declined meeting",
                    "start": {"dateTime": "2026-08-18T10:00:00-03:00"},
                    "attendees": [{"self": True, "responseStatus": "declined"}],
                },
                {
                    "id": "birthday",
                    "iCalUID": "birthday",
                    "summary": "Birthday",
                    "eventType": "birthday",
                    "start": {"dateTime": "2026-08-18T11:00:00-03:00"},
                },
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "Accepted meeting" in report
    assert "Declined meeting" not in report
    assert "Birthday" not in report


@pytest.mark.parametrize(
    "free_event_field, free_event_value",
    [
        ("availability", "free"),
        ("showAs", "free"),
        ("transparency", "transparent"),
    ],
)
def test_report_omits_free_events_and_keeps_busy_events(
    free_event_field: str, free_event_value: str
) -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "accepted",
                    "summary": "Team sync",
                    "start": {"dateTime": "2026-08-18T09:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
                {
                    "id": "tentative",
                    "summary": "Tentative planning",
                    "start": {"dateTime": "2026-08-18T10:00:00+00:00"},
                    "attendees": [{"self": True, "responseStatus": "tentative"}],
                },
                {
                    "id": "free",
                    "summary": "Reveja as Relações Humanas",
                    "start": {"dateTime": "2026-08-18T11:00:00+00:00"},
                    free_event_field: free_event_value,
                    "attendees": [{"self": True, "responseStatus": "accepted"}],
                },
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
    )

    assert "| 09:00 | Team sync | Work |  |" in report
    assert "| 10:00 | Tentative planning | Work | ❓ |" in report
    assert "Reveja as Relações Humanas" not in report


def test_report_honors_calendar_days_and_all_day_events() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "offsite",
                    "summary": "Offsite | planning",
                    "start": {"date": "2026-08-20"},
                }
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Work")],
        now=now,
        timezone=timezone,
        calendar_days=3,
    )

    expected_date = datetime(2026, 8, 20).strftime("%d/%m (%A)")
    assert expected_date in report
    assert "All day | Offsite \\| planning" in report
