"""Trading-domain models for the broker-neutral trade flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum

from quintet.broker.models import BrokerOrder, BrokerPosition


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Side(str, Enum):
    """Trade direction."""

    LONG = "long"
    SHORT = "short"

    @property
    def entry_action(self) -> str:
        return "BUY" if self is Side.LONG else "SELL"

    @property
    def protective_action(self) -> str:
        return "SELL" if self is Side.LONG else "BUY"

    @property
    def exit_action(self) -> str:
        return self.protective_action

    @classmethod
    def coerce(cls, value: Side | str) -> Side:
        if isinstance(value, cls):
            return value
        return cls(str(value).lower())

    @classmethod
    def from_config(cls, value: str) -> Side:
        return cls.coerce(value)


TradeKey = tuple[int, str]  # (con_id, system)


@dataclass(frozen=True)
class SignalCandidate:
    """Actionable signal candidate produced by the signal pipeline."""

    system: str
    side: Side
    symbol: str
    local_symbol: str
    con_id: int
    exchange: str
    currency: str
    multiplier: float
    min_tick: float
    price_magnifier: int
    entry_price: float
    stop_price: float
    current_price: float | None = None
    prob: float | None = None
    tau: float | None = None
    cluster_id: int | None = None
    high: float | None = None
    rspos: float | None = None
    last_day: date | None = None
    contract_month: str | None = None

    @property
    def key(self) -> TradeKey:
        return (self.con_id, self.system)


@dataclass(frozen=True)
class RiskExposure:
    """Open-position exposure used for pooled portfolio risk."""

    con_id: int
    system: str
    side: Side
    quantity: float
    current_price: float
    stop_price: float
    multiplier: float
    price_magnifier: int = 1


@dataclass(frozen=True)
class RiskState:
    """Account-level risk inputs used for sizing new entries."""

    net_liquidation: float
    portfolio_risk: float = 0.0
    risk_budget_by_system: dict[str, float] = field(default_factory=dict)

    @property
    def account_equity(self) -> float:
        return self.net_liquidation

    @property
    def free_equity(self) -> float:
        return self.net_liquidation - self.portfolio_risk

    def budget_for(self, system: str) -> float:
        return self.risk_budget_by_system.get(system, 0.0)


@dataclass(frozen=True)
class ReconciledTradeState:
    """Broker state classified into planner-friendly buckets."""

    positions_by_key: dict[TradeKey, BrokerPosition] = field(default_factory=dict)
    entry_orders_by_key: dict[TradeKey, BrokerOrder] = field(default_factory=dict)
    protective_stops_by_key: dict[TradeKey, BrokerOrder] = field(default_factory=dict)
    orphaned_orders: list[BrokerOrder] = field(default_factory=list)
    positions_without_protective_stop: list[BrokerPosition] = field(default_factory=list)
    unknown_system_positions: list[BrokerPosition] = field(default_factory=list)
    external_or_unclassified_orders: list[BrokerOrder] = field(default_factory=list)


@dataclass(frozen=True)
class MaintenancePlan:
    """Signal-independent intents and alerts."""

    generated_at: datetime = field(default_factory=_utc_now)
    intents: list[object] = field(default_factory=list)


@dataclass(frozen=True)
class TradePlan:
    """Complete broker-neutral plan for one dry-run/live execution."""

    generated_at: datetime = field(default_factory=_utc_now)
    signals: list[SignalCandidate] = field(default_factory=list)
    intents: list[object] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    maintenance: MaintenancePlan | None = None
