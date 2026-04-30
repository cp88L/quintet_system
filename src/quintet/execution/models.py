"""Broker-neutral execution intent and report models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from quintet.trading.models import Side, TradeKey


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ExecutionStatus(str, Enum):
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    CANCEL_REQUESTED = "cancel_requested"
    DRY_RUN = "dry_run"
    EXIT_SUBMITTED = "exit_submitted"
    MODIFIED = "modified"
    MODIFY_THREW = "modify_threw"
    PLACE_THREW = "place_threw"
    EXIT_THREW = "exit_threw"
    CANCEL_THREW = "cancel_threw"
    REPORTED = "reported"


@dataclass(frozen=True)
class PlaceBracketIntent:
    """Intent to place a parent entry plus child protective stop."""

    key: TradeKey
    side: Side
    symbol: str
    local_symbol: str
    exchange: str
    currency: str
    quantity: int
    entry_action: str
    entry_order_type: str
    entry_stop_price: float
    entry_limit_price: float
    protective_action: str
    protective_order_type: str
    protective_stop_price: float
    protective_limit_price: float | None
    risk_per_contract: float
    total_risk: float
    reason: str = "new_signal"


@dataclass(frozen=True)
class CancelOrderIntent:
    """Intent to cancel one broker order."""

    order_id: int
    key: TradeKey | None = None
    reason: str = "cancel"


@dataclass(frozen=True)
class ModifyOrderIntent:
    """Intent to modify one broker order."""

    order_id: int
    key: TradeKey | None = None
    aux_price: float | None = None
    limit_price: float | None = None
    reason: str = "modify"


@dataclass(frozen=True)
class ExitPositionIntent:
    """Intent to exit an existing position."""

    key: TradeKey
    side: Side
    symbol: str
    local_symbol: str
    quantity: int
    exchange: str = ""
    currency: str = "USD"
    reason: str = "exit"


@dataclass(frozen=True)
class RollEntryIntent:
    """Report-only intent describing a conditional roll entry."""

    old_key: TradeKey
    new_key: TradeKey
    side: Side
    symbol: str
    old_local_symbol: str
    new_local_symbol: str
    exchange: str
    currency: str
    quantity: int
    rspos: float
    threshold: float
    protective_stop_price: float
    parent_order_type: str = "MKT"
    protective_order_type: str = "STP"
    reason: str = "last_day_roll"


@dataclass(frozen=True)
class AlertIntent:
    """Report-only alert produced by planning."""

    code: str
    message: str
    key: TradeKey | None = None
    level: AlertLevel = AlertLevel.WARNING
    operator_action: str | None = None


@dataclass(frozen=True)
class ExecutionEvent:
    """Single execution outcome or callback event."""

    status: ExecutionStatus | str
    intent: str
    order_id: int | None = None
    key: TradeKey | None = None
    message: str | None = None


@dataclass(frozen=True)
class ExecutionCounts:
    """Operator-facing execution outcome totals."""

    submitted: int = 0
    cancel_requested: int = 0
    modified: int = 0
    reported_only: int = 0
    alerts: int = 0
    threw: int = 0
    dry_run: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class ExecutionReport:
    """Result of dry-run or live execution."""

    generated_at: datetime
    mode: str
    submitted: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    open_orders_after: list[dict] = field(default_factory=list)
    events: list[ExecutionEvent] = field(default_factory=list)
    counts: ExecutionCounts = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "counts",
            summarize_execution_counts(
                submitted=self.submitted,
                skipped=self.skipped,
                alerts=self.alerts,
                events=self.events,
            ),
        )


def summarize_execution_counts(
    *,
    submitted: list[dict],
    skipped: list[dict],
    alerts: list[dict],
    events: list[ExecutionEvent],
) -> ExecutionCounts:
    """Compute stable JSON/CLI counts from the report sections."""
    status_counts: dict[str, int] = {}
    for record in submitted:
        status = _status_value(record.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1

    event_statuses = [_status_value(event.status) for event in events]
    submitted_count = status_counts.get(ExecutionStatus.SUBMITTED.value, 0)
    submitted_count += status_counts.get(ExecutionStatus.EXIT_SUBMITTED.value, 0)
    reported_only = status_counts.get(ExecutionStatus.REPORTED.value, 0)
    reported_only += sum(
        1 for status in event_statuses if status == ExecutionStatus.REPORTED.value
    )
    threw = sum(
        count for status, count in status_counts.items() if status.endswith("_threw")
    )
    threw += sum(1 for status in event_statuses if status.endswith("_threw"))

    return ExecutionCounts(
        submitted=submitted_count,
        cancel_requested=status_counts.get(ExecutionStatus.CANCEL_REQUESTED.value, 0),
        modified=status_counts.get(ExecutionStatus.MODIFIED.value, 0),
        reported_only=reported_only,
        alerts=len(alerts),
        threw=threw,
        dry_run=status_counts.get(ExecutionStatus.DRY_RUN.value, 0),
        skipped=len(skipped),
    )


def _status_value(status: object) -> str:
    if isinstance(status, ExecutionStatus):
        return status.value
    if status is None:
        return ""
    return str(status)
