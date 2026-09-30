import json
import locale
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from daily_calendar.cli import (
    calendar_fetch_range,
    fetch_calendar_events,
    load_holidays,
    main,
    parse_args,
    parse_calendar_response,
    parse_calendar_sources,
)
from daily_calendar.report import (
    CalendarSource,
    build_report_markdown,
    markdown_cell,
    markdown_to_html,
)


def test_holiday_section_starts_after_configured_calendar_window() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "id": "event-1",
                    "summary": "Release planning",
                    "start": {"dateTime": "2026-08-20T09:00:00+00:00"},
                }
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Fixture")],
        now=now,
        timezone=timezone,
        holidays={"2026-08-20": "Example holiday"},
        calendar_days=3,
    )

    assert report.count("Release planning") == 1


def test_html_table_preserves_escaped_pipe_inside_cell() -> None:
    rendered = markdown_to_html(
        """| Time | Event |
|------|-------|
| 09:00 | Design \\| review |
"""
    )

    assert rendered.count("<td>") == 2
    assert "<td>Design | review</td>" in rendered


def test_html_table_preserves_literal_backslashes() -> None:
    rendered = markdown_to_html(
        """| Path |
|------|
| C:\\Temp\\file |
"""
    )

    assert "<td>C:\\Temp\\file</td>" in rendered


def test_markdown_cell_truncates_before_escaping_pipes() -> None:
    assert markdown_cell("abcd|rest", limit=5) == "abcd\\|"


@pytest.mark.parametrize(
    "value",
    [
        {"not-a-date": "Holiday"},
        {"20260820": "Holiday"},
        {"2026-12-25": ""},
        {"2026-12-25": 25},
        {"2026-12-25": "Holiday\n## Forged section"},
        {"2026-12-25": "Holiday\u2028## Forged section"},
    ],
)
def test_holiday_file_rejects_invalid_entries(tmp_path: Path, value: object) -> None:
    holidays_path = tmp_path / "holidays.json"
    holidays_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="holidays file"):
        load_holidays(str(holidays_path))


@pytest.mark.parametrize("value", [{}, {"events": {}}, {"events": [1]}])
def test_calendar_response_requires_an_event_list(value: object) -> None:
    with pytest.raises(ValueError, match="calendar response"):
        parse_calendar_response(json.dumps(value))


def test_calendar_response_accepts_gog_all_day_start_fields() -> None:
    response = parse_calendar_response(
        json.dumps(
            {
                "events": [
                    {
                        "summary": "All-day fixture",
                        "start": {"date": "2026-08-21"},
                        "startLocal": "2026-08-21",
                    }
                ]
            }
        )
    )

    assert response["events"][0]["start"]["date"] == "2026-08-21"


@pytest.mark.parametrize(
    "event",
    [
        {"start": None},
        {"start": {}},
        {"start": {"date": "not-a-date"}},
        {"start": {"dateTime": "not-a-datetime"}},
        {"start": {"dateTime": "2026-08-18"}},
        {"start": {"date": "2026-08-18", "dateTime": "not-a-datetime"}},
        {"attendees": None},
        {"organizer": []},
        {"creator": "fixture"},
    ],
)
def test_calendar_response_rejects_invalid_nested_shapes(event: object) -> None:
    with pytest.raises(ValueError, match="calendar response"):
        parse_calendar_response(json.dumps({"events": [event]}))


def test_duplicate_calendar_accounts_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate calendar account"):
        parse_calendar_sources(["fixture=First"], "fixture=Second")


def test_calendar_accounts_rejects_whitespace_only_environment_value() -> None:
    with pytest.raises(ValueError, match="at least one calendar account"):
        parse_calendar_sources([], " ,  ")


def test_main_reports_configuration_errors_without_traceback(capsys: pytest.CaptureFixture) -> None:
    assert main(["--calendar-account", "invalid", "--timezone", "UTC"]) == 1

    error = capsys.readouterr().err
    assert "invalid calendar account entry" in error
    assert "Traceback" not in error


@pytest.mark.parametrize("option", ["--calendar-days", "--holiday-days"])
def test_main_rejects_unrepresentable_day_ranges_without_traceback(
    option: str, capsys: pytest.CaptureFixture
) -> None:
    with pytest.raises(SystemExit):
        main(["--calendar-account", "fixture=Fixture", option, "1000000000"])

    error = capsys.readouterr().err
    assert option in error
    assert "Traceback" not in error


def test_events_without_ids_remain_distinct() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    events_by_account = {
        "fixture": {
            "events": [
                {
                    "summary": summary,
                    "start": {"dateTime": f"2026-08-18T{hour}:00:00+00:00"},
                }
                for summary, hour in [("First event", "09"), ("Second event", "10")]
            ]
        }
    }

    report = build_report_markdown(
        events_by_account,
        [CalendarSource(account="fixture", label="Fixture")],
        now=now,
        timezone=timezone,
    )

    assert "First event" in report
    assert "Second event" in report


def test_shared_holiday_event_is_deduplicated_across_calendars() -> None:
    timezone = ZoneInfo("UTC")
    now = datetime(2026, 8, 18, 8, 0, tzinfo=timezone)
    shared_event = {
        "iCalUID": "shared-event",
        "summary": "Shared planning",
        "start": {"dateTime": "2026-08-21T09:00:00+00:00"},
    }

    report = build_report_markdown(
        {"fixture-first": {"events": [shared_event]}, "fixture-second": {"events": [shared_event]}},
        [
            CalendarSource(account="fixture-first", label="First"),
            CalendarSource(account="fixture-second", label="Second"),
        ],
        now=now,
        timezone=timezone,
        holidays={"2026-08-21": "Example holiday"},
    )

    assert report.count("Shared planning") == 1
    assert "First, Second" in report


def test_calendar_fetch_range_only_extends_for_configured_holidays() -> None:
    today = datetime(2026, 8, 18).date()

    assert calendar_fetch_range(today, calendar_days=2, holiday_days=28, has_holidays=False) == (
        today,
        datetime(2026, 8, 20).date(),
    )
    assert calendar_fetch_range(today, calendar_days=2, holiday_days=28, has_holidays=True) == (
        today,
        datetime(2026, 9, 16).date(),
    )


def test_calendar_fetch_uses_complete_explicit_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_command: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        captured_command.extend(command)
        return SimpleNamespace(stdout='{"events": []}')

    monkeypatch.setattr("daily_calendar.cli.subprocess.run", fake_run)

    fetch_calendar_events(
        "gog",
        "fixture",
        start=datetime(2026, 8, 18).date(),
        end=datetime(2026, 8, 20).date(),
        timezone=ZoneInfo("UTC"),
    )

    assert captured_command == [
        "gog",
        "calendar",
        "list",
        "-a",
        "fixture",
        "--from",
        "2026-08-18",
        "--to",
        "2026-08-20",
        "--timezone",
        "UTC",
        "--all-pages",
        "--no-input",
        "--json",
    ]


def test_bundled_2027_movable_holidays_match_easter_calendar() -> None:
    holidays_path = Path(__file__).parents[1] / "examples" / "holidays-br-sp-2026-2027.json"

    holidays = load_holidays(str(holidays_path))

    assert holidays["2027-02-09"] == "Carnaval"
    assert holidays["2027-03-26"] == "Sexta-feira Santa"
    assert holidays["2027-05-27"] == "Corpus Christi"


def test_bundled_sao_paulo_calendar_covers_both_full_years() -> None:
    holidays_path = Path(__file__).parents[1] / "examples" / "holidays-br-sp-2026-2027.json"

    holidays = load_holidays(str(holidays_path))

    assert holidays["2026-01-01"] == "Ano Novo"
    assert holidays["2026-07-09"] == "Data Magna do Estado de Sao Paulo"
    assert holidays["2027-07-09"] == "Data Magna do Estado de Sao Paulo"
    assert holidays["2027-12-25"] == "Natal"


def test_timezone_is_required_without_tz_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.delenv("DAILY_CALENDAR_TIMEZONE", raising=False)

    with pytest.raises(SystemExit):
        parse_args(["--calendar-account", "calendar=Calendar"])


def test_timezone_uses_tz_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Europe/Lisbon")

    args = parse_args(["--calendar-account", "calendar=Calendar"])

    assert args.timezone == "Europe/Lisbon"


def test_main_reports_invalid_process_locale(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        "daily_calendar.cli.locale.setlocale",
        lambda *_args: (_ for _ in ()).throw(locale.Error("unsupported locale")),
    )

    assert main(["--calendar-account", "fixture=Calendar", "--timezone", "UTC"]) == 1
    assert "unsupported locale" in capsys.readouterr().err
