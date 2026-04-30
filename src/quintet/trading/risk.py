"""Risk and sizing helpers for broker-neutral trade planning."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from math import isfinite

from quintet.config import HEAT
from quintet.trading.models import RiskExposure, RiskState, Side


def risk_per_contract(
    entry_price: float,
    stop_price: float,
    multiplier: float,
    price_magnifier: int = 1,
) -> float:
    """Dollar risk per one contract from entry to protective stop."""
    _require_positive("multiplier", multiplier)
    _require_positive("price_magnifier", price_magnifier)
    return abs(entry_price - stop_price) / price_magnifier * multiplier


def calculate_contract_risk(
    entry_price: float,
    stop_price: float,
    multiplier: float,
    price_magnifier: int = 1,
) -> float:
    """Alias for one-contract dollar risk."""

    return risk_per_contract(entry_price, stop_price, multiplier, price_magnifier)


def calculate_position_size(
    risk_budget: float,
    entry_price: float,
    stop_price: float,
    multiplier: float,
    price_magnifier: int = 1,
) -> int:
    """Maximum whole contracts allowed by the risk budget."""
    per_contract = risk_per_contract(
        entry_price, stop_price, multiplier, price_magnifier
    )
    if per_contract <= 0 or per_contract > risk_budget:
        return 0
    return math.floor(risk_budget / per_contract)


def calculate_position_risk(
    side: Side | str,
    current_price: float,
    stop_price: float,
    quantity: int,
    multiplier: float,
    price_magnifier: int = 1,
) -> float:
    """Open risk for a position against its protective stop."""
    _require_positive("multiplier", multiplier)
    _require_positive("price_magnifier", price_magnifier)

    trade_side = Side.coerce(side)
    if trade_side is Side.LONG:
        price_diff = max(0.0, current_price - stop_price)
    else:
        price_diff = max(0.0, stop_price - current_price)
    return price_diff / price_magnifier * multiplier * abs(quantity)


def calculate_portfolio_risk(positions: Iterable[RiskExposure]) -> float:
    """Sum side-aware open risk across all systems."""

    return sum(
        calculate_position_risk(
            side=position.side,
            current_price=position.current_price,
            stop_price=position.stop_price,
            quantity=position.quantity,
            multiplier=position.multiplier,
            price_magnifier=position.price_magnifier,
        )
        for position in positions
    )


def calculate_risk_budget(
    risk_state: RiskState | None = None,
    system: str | None = None,
    heat_by_system: Mapping[str, float] | None = None,
    *,
    account_equity: float | None = None,
    positions: Iterable[RiskExposure] = (),
) -> float | RiskState:
    """Calculate one system budget or a full pooled `RiskState`.

    Existing planner code can pass `(risk_state, system)` to get a single
    budget. Newer pure-risk code can pass `account_equity`, `positions`, and
    `heat_by_system` to get all per-system budgets from the same equity pool.
    """

    heat_by_system = heat_by_system or HEAT
    if risk_state is not None:
        if system is None:
            raise ValueError("system is required when risk_state is supplied")
        return max(0.0, risk_state.free_equity * heat_by_system[system])

    if account_equity is None:
        raise ValueError("account_equity is required when risk_state is not supplied")

    return build_risk_state(
        account_equity=account_equity,
        positions=positions,
        heat_by_system=heat_by_system,
    )


def build_risk_state(
    *,
    account_equity: float,
    positions: Iterable[RiskExposure] = (),
    heat_by_system: Mapping[str, float] | None = None,
) -> RiskState:
    """Build pooled risk state from current open-position exposure."""
    heat_by_system = heat_by_system or HEAT
    portfolio_risk = calculate_portfolio_risk(positions)
    free_equity = account_equity - portfolio_risk
    budgets = {
        heat_system: max(0.0, free_equity * heat)
        for heat_system, heat in heat_by_system.items()
    }
    return RiskState(
        net_liquidation=account_equity,
        portfolio_risk=portfolio_risk,
        risk_budget_by_system=budgets,
    )


def _require_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
