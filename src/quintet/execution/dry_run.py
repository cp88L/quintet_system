"""Dry-run executor for broker-neutral trade plans."""

from __future__ import annotations

from datetime import datetime

from quintet.execution.models import (
    AlertIntent,
    ExecutionReport,
    ExecutionStatus,
    LastDayCloseoutIntent,
    summarize_roll_entry,
)
from quintet.execution.serialize import to_plain
from quintet.trading.models import TradePlan


class DryRunExecutor:
    """Executor that records what would happen without broker side effects."""

    mode = "dry_run"

    def execute(self, plan: TradePlan) -> ExecutionReport:
        submitted: list[dict] = []
        alerts: list[dict] = []
        for intent in plan.intents:
            payload = to_plain(intent)
            if isinstance(intent, AlertIntent):
                alerts.append(payload)
            else:
                record = {"status": ExecutionStatus.DRY_RUN.value, "intent": payload}
                if isinstance(intent, LastDayCloseoutIntent):
                    roll_summary = summarize_roll_entry(intent.roll_entry)
                    if roll_summary is not None:
                        record["roll_summary"] = roll_summary
                submitted.append(record)
        return ExecutionReport(
            generated_at=datetime.now(),
            mode=self.mode,
            submitted=submitted,
            skipped=plan.skipped,
            alerts=alerts,
        )
