"""Write latest trade-flow reports."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path


class ReportStore:
    """Writes latest trade plan and execution report JSON files."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)

    @property
    def trade_plan_path(self) -> Path:
        return self.directory / "latest_trade_plan.json"

    @property
    def execution_report_path(self) -> Path:
        return self.directory / "latest_execution_report.json"

    def write_trade_plan(self, plan) -> Path:
        return self._write(self.trade_plan_path, plan)

    def write_execution_report(self, report) -> Path:
        return self._write(self.execution_report_path, report)

    def _write(self, path: Path, payload) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(_to_plain(payload), f, indent=2)
        return path


def _to_plain(value):
    if is_dataclass(value):
        return {k: _to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    return value
