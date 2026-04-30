"""JSON-safe conversion helpers for execution reports."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum


def to_plain(value):
    """Convert dataclasses/enums/tuples into plain JSON-compatible values."""
    if is_dataclass(value):
        return {k: to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    return value
