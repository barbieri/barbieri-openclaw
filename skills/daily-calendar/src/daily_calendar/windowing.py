from __future__ import annotations

from datetime import date, timedelta


def effective_report_day_count(today: date, calendar_days: int) -> int:
    if calendar_days < 1:
        raise ValueError("calendar_days must be at least 1")
    if today.weekday() == 4:
        days_through_sunday = (6 - today.weekday()) + 1
        return max(calendar_days, days_through_sunday)
    return calendar_days


def calendar_fetch_range(today: date, *, calendar_days: int) -> tuple[date, date]:
    days = effective_report_day_count(today, calendar_days)
    return today, today + timedelta(days=days)
