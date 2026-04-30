"""IBKR trading-calendar parsing helpers."""

from __future__ import annotations

import re
from datetime import date, datetime


def parse_next_rth_day(liquid_hours: str) -> date | None:
    """Parse the next regular trading session date from IBKR liquidHours."""
    if not liquid_hours:
        return None
    pattern = r"(\d{8}):\d{4}-(?:\d{8}:)?\d{4}"
    matches = re.findall(pattern, liquid_hours)
    if not matches:
        return None
    return datetime.strptime(matches[0], "%Y%m%d").date()
