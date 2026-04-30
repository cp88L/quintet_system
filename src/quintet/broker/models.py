"""Broker-neutral state models.

These dataclasses intentionally contain no IBKR SDK objects. Broker adapters
map raw API callbacks into these structures before trading logic sees them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class BrokerOrderAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class BrokerOrderType(str, Enum):
    MKT = "MKT"
    LMT = "LMT"
    STP = "STP"
    STP_LMT = "STP LMT"
    UNKNOWN = "UNKNOWN"


class BrokerOrderStatus(str, Enum):
    PENDING_SUBMIT = "PendingSubmit"
    PRESUBMITTED = "PreSubmitted"
    SUBMITTED = "Submitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    INACTIVE = "Inactive"
    UNKNOWN = "Unknown"


class BrokerErrorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class AccountState:
    """Subset of account values needed by trade planning."""

    net_liquidation: float
    currency: str = "USD"
    account_id: str | None = None
    buying_power: float | None = None
    raw_values: dict[str, str | float] = field(default_factory=dict)


@dataclass(frozen=True)
class ContractMeta:
    """Contract metadata required for sizing and valid order prices."""

    con_id: int
    symbol: str
    local_symbol: str
    exchange: str
    currency: str
    multiplier: float
    min_tick: float
    price_magnifier: int = 1
    last_trade_date: date | None = None
    last_day: date | None = None


@dataclass(frozen=True)
class BrokerPosition:
    """Open broker position as reported by the broker."""

    account: str
    con_id: int
    symbol: str
    local_symbol: str
    quantity: float
    avg_cost: float
    market_price: float | None = None
    market_value: float | None = None


@dataclass(frozen=True)
class BrokerOrder:
    """Open broker order, normalized from broker-specific order objects."""

    order_id: int
    con_id: int
    symbol: str
    local_symbol: str
    action: BrokerOrderAction | str
    order_type: BrokerOrderType | str
    quantity: int
    status: BrokerOrderStatus | str
    exchange: str = ""
    currency: str = ""
    system: str | None = None
    aux_price: float | None = None
    limit_price: float | None = None
    parent_id: int | None = None
    perm_id: int | None = None
    oca_group: str | None = None
    oca_type: int | None = None
    order_ref: str | None = None
    tif: str | None = None
    outside_rth: bool | None = None
    transmit: bool | None = None


@dataclass(frozen=True)
class BrokerFill:
    """Execution/fill record captured during a broker session."""

    exec_id: str
    order_id: int
    con_id: int
    symbol: str
    local_symbol: str
    side: str
    quantity: int
    price: float
    time: str
    order_ref: str | None = None


@dataclass(frozen=True)
class BrokerError:
    """Broker error associated with a request/order id."""

    request_id: int
    code: int
    message: str
    timestamp: datetime
    severity: BrokerErrorSeverity = BrokerErrorSeverity.ERROR


@dataclass(frozen=True)
class BrokerState:
    """Current broker/account state collected for one trade-flow run."""

    collected_at: datetime
    account: AccountState
    positions: list[BrokerPosition] = field(default_factory=list)
    open_orders: list[BrokerOrder] = field(default_factory=list)
    recent_fills: list[BrokerFill] = field(default_factory=list)
    recent_errors: list[BrokerError] = field(default_factory=list)
    next_rth_days: dict[int, date] = field(default_factory=dict)
    contract_meta: dict[int, ContractMeta] = field(default_factory=dict)
