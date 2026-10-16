from datetime import date

from daily_calendar.windowing import calendar_fetch_range, effective_report_day_count


def test_friday_window_extends_through_sunday() -> None:
    friday = date(2026, 10, 16)

    assert effective_report_day_count(friday, 2) == 3
    assert calendar_fetch_range(friday, calendar_days=2) == (
        friday,
        date(2026, 10, 19),
    )


def test_non_friday_keeps_default_window() -> None:
    thursday = date(2026, 10, 15)

    assert effective_report_day_count(thursday, 2) == 2
    assert calendar_fetch_range(thursday, calendar_days=2) == (
        thursday,
        date(2026, 10, 17),
    )
