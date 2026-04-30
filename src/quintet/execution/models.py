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


@dataclass(frozen=True)
class ExecutionEvent:
    """Single execution outcome or callback event."""

    status: ExecutionStatus | str
    intent: str
    order_id: int | None = None
    key: TradeKey | None = None
    message: str | None = None


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
