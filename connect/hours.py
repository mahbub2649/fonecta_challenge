"""The hours format used everywhere: 'closed', '10:00-15:00' or '10:00-14:00,17:00-22:00'."""
from __future__ import annotations

import re

_HOURS_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


def to_minutes(text: str) -> int:
    return int(text[:2]) * 60 + int(text[3:])


def from_minutes(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def is_valid(hours: str) -> bool:
    """Accept 'closed' or ordered intervals with a gap between them, as Yext requires. A close past midnight is allowed."""
    if hours == "closed":
        return True
    if not isinstance(hours, str) or not hours:
        return False
    spans = []
    for part in hours.split(","):
        if not _HOURS_RE.match(part):
            return False
        start, end = (to_minutes(x) for x in part.split("-"))
        if start == end:
            return False
        spans.append((start, end if end > start else end + 1440))
    return all(a[1] < b[0] for a, b in zip(spans, spans[1:]))


def day_to_string(obj: dict | None) -> str:
    """Yext day object to our format."""
    if not obj or obj.get("isClosed"):
        return "closed"
    return ",".join(f"{i['start']}-{i['end']}" for i in obj.get("openIntervals", [])) or "closed"


def string_to_day(hours: str) -> dict:
    """Our format to a Yext day object."""
    if hours == "closed":
        return {"isClosed": True}
    return {"openIntervals": [{"start": a, "end": b} for a, b in (p.split("-") for p in hours.split(","))]}


def shift(hours: str, open_by: int, close_by: int) -> str:
    """Move the first opening and the last closing, or return the input if that would break the hours."""
    if hours == "closed" or (not open_by and not close_by):
        return hours
    parts = [p.split("-") for p in hours.split(",")]
    parts[0][0] = from_minutes(to_minutes(parts[0][0]) + open_by)
    parts[-1][1] = from_minutes(to_minutes(parts[-1][1]) + close_by)
    result = ",".join("-".join(p) for p in parts)
    return result if is_valid(result) else hours


def edit_shift(proposed: str, final: str) -> tuple[int, int]:
    """How far an owner moved the opening and closing. (0, 0) if either side is closed."""
    if proposed == "closed" or final == "closed":
        return 0, 0
    first_a, last_a = proposed.split(",")[0].split("-")[0], proposed.split(",")[-1].split("-")[1]
    first_b, last_b = final.split(",")[0].split("-")[0], final.split(",")[-1].split("-")[1]
    return to_minutes(first_b) - to_minutes(first_a), to_minutes(last_b) - to_minutes(last_a)
