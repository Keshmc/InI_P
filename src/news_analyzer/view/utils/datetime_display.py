"""Display formatting for date/time values in Swiss local timezone."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

SWISS_TZ = ZoneInfo("Europe/Zurich")


def format_swiss_date_time(value: Any) -> tuple[str, str]:
    """Format input value into (dd.mm.yyyy, hh:mm) in Europe/Zurich timezone."""
    parsed = _parse_datetime(value)
    if parsed is None:
        return "-", "-"

    swiss_dt = parsed.astimezone(SWISS_TZ)
    return swiss_dt.strftime("%d.%m.%Y"), swiss_dt.strftime("%H:%M")


def format_swiss_timestamp(value: Any) -> str:
    """Format input value to 'dd.mm.yyyy | hh:mm' in Europe/Zurich timezone."""
    date_value, time_value = format_swiss_date_time(value)
    if date_value == "-" or time_value == "-":
        return "-"
    return f"{date_value} | {time_value}"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = date_parser.parse(text)
        except Exception:  # noqa: BLE001
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
