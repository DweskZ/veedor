"""Plausibility ranges for values read from tools (pure).

A value outside its range is not shown: the sentence says it is out of range in the source and the
tool log records it. A zero is treated as missing data, like everywhere else in the project: a
company's equity, assets, revenue, capital or headcount of exactly zero is not a reported figure.

| Field | Accepted |
|---|---|
| dates (incorporation, activity start, cessation) | 1900-01-01 to the day of the query |
| balance / fiscal year | 1900 to the current year |
| subscribed capital | more than 0 and at most USD 1e12 |
| equity | USD -1e12 to 1e12, not 0 |
| assets | more than 0 and at most USD 1e12 |
| employees | 1 to 1,000,000 |
| amounts of awards between two parties | 0 to USD 1e12 |
"""

from __future__ import annotations

from datetime import date

DATE_MIN = date(1900, 1, 1)
MAX_USD = 1e12
MAX_EMPLOYEES = 1_000_000


def amount(
    name: str, value: float | None, rejected: list[str], *, allow_negative: bool = False
) -> float | None:
    """The value rounded to cents, None when missing or zero, None and recorded when out of range."""
    if value is None or value == 0:
        return None
    low = -MAX_USD if allow_negative else 0.0
    if not (low <= value <= MAX_USD):
        rejected.append(name)
        return None
    return round(float(value), 2)


def count(name: str, value: int | None, rejected: list[str]) -> int | None:
    if value is None or value == 0:
        return None
    if not (1 <= value <= MAX_EMPLOYEES):
        rejected.append(name)
        return None
    return int(value)


def day(name: str, value: date | None, today: date, rejected: list[str]) -> date | None:
    if value is None:
        return None
    if not (DATE_MIN <= value <= today):
        rejected.append(name)
        return None
    return value


def year(name: str, value: int | None, today: date, rejected: list[str]) -> int | None:
    if value is None:
        return None
    if not (DATE_MIN.year <= value <= today.year):
        rejected.append(name)
        return None
    return value
