"""Pure trade planning from signals and reconciled broker state."""

from __future__ import annotations

from quintet.config import LIMIT_OFFSET
from quintet.execution.models import (
    CancelOrderIntent,
    ModifyOrderIntent,
    PlaceBracketIntent,
)
from quintet.trading.models import (
    MaintenancePlan,
    ReconciledTradeState,
    RiskState,
    SignalCandidate,
    Side,
    TradePlan,
)
from quintet.trading.prices import round_to_tick
from quintet.trading.risk import (
    calculate_position_size,
    calculate_risk_budget,
    risk_per_contract,
)


def build_trade_plan(
    *,
    signals: list[SignalCandidate],
    state: ReconciledTradeState,
    maintenance: MaintenancePlan,
    risk_state: RiskState,
) -> TradePlan:
    """Build a broker-neutral trade plan."""
    intents: list[object] = list(maintenance.intents)
    skipped: list[dict] = []
    signals_by_key = {signal.key: signal for signal in signals}

    for key, order in state.entry_orders_by_key.items():
        signal = signals_by_key.get(key)
        if signal is None:
            intents.append(
                CancelOrderIntent(
                    order_id=order.order_id,
                    key=key,
                    reason="signal_disappeared",
                )
            )
            continue
        entry_stop = round_to_tick(signal.entry_price, signal.min_tick)
        if order.aux_price is not None and order.aux_price != entry_stop:
            intents.append(
                ModifyOrderIntent(
                    order_id=order.order_id,
                    key=key,
                    aux_price=entry_stop,
                    limit_price=_entry_limit(signal),
                    reason="entry_level_changed",
                )
            )

    for key, position in state.positions_by_key.items():
        signal = signals_by_key.get(key)
        stop = state.protective_stops_by_key.get(key)
        if signal is None or stop is None:
            continue
        stop_aux = round_to_tick(signal.stop_price, signal.min_tick)
        if stop.aux_price is not None and stop.aux_price != stop_aux:
            intents.append(
                ModifyOrderIntent(
                    order_id=stop.order_id,
                    key=key,
                    aux_price=stop_aux,
                    limit_price=_stop_limit(signal),
                    reason="position_stop_level_changed",
                )
            )

    for signal in signals:
        key = signal.key
        if key in state.positions_by_key:
            skipped.append(_skip(signal, "already_has_position"))
            continue
        if key in state.entry_orders_by_key:
            skipped.append(_skip(signal, "already_has_entry_order"))
            continue

        budget = calculate_risk_budget(risk_state, signal.system)
        per_contract = risk_per_contract(
            signal.entry_price,
            signal.stop_price,
            signal.multiplier,
            signal.price_magnifier,
        )
        quantity = calculate_position_size(
            budget,
            signal.entry_price,
            signal.stop_price,
            signal.multiplier,
            signal.price_magnifier,
        )
        if quantity <= 0:
            skipped.append(_skip(signal, "insufficient_risk_budget"))
            continue

        intents.append(
            PlaceBracketIntent(
                key=key,
                side=signal.side,
                symbol=signal.symbol,
                local_symbol=signal.local_symbol,
                exchange=signal.exchange,
                currency=signal.currency,
                quantity=quantity,
                entry_action=signal.side.entry_action,
                entry_order_type="STP LMT",
                entry_stop_price=round_to_tick(signal.entry_price, signal.min_tick),
                entry_limit_price=_entry_limit(signal),
                protective_action=signal.side.protective_action,
                protective_order_type="STP LMT",
                protective_stop_price=round_to_tick(signal.stop_price, signal.min_tick),
                protective_limit_price=_stop_limit(signal),
                risk_per_contract=per_contract,
                total_risk=per_contract * quantity,
            )
        )

    return TradePlan(
        signals=signals,
        intents=intents,
        skipped=skipped,
        maintenance=maintenance,
    )


def _entry_limit(signal: SignalCandidate) -> float:
    multiplier = 1 + LIMIT_OFFSET if signal.side is Side.LONG else 1 - LIMIT_OFFSET
    return round_to_tick(signal.entry_price * multiplier, signal.min_tick)


def _stop_limit(signal: SignalCandidate) -> float:
    multiplier = 1 - LIMIT_OFFSET if signal.side is Side.LONG else 1 + LIMIT_OFFSET
    return round_to_tick(signal.stop_price * multiplier, signal.min_tick)


def _skip(signal: SignalCandidate, reason: str) -> dict:
    return {
        "key": [signal.con_id, signal.system],
        "symbol": signal.symbol,
        "local_symbol": signal.local_symbol,
        "reason": reason,
    }
