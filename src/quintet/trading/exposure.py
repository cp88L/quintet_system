"""Build risk exposure from reconciled broker state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from quintet.config import SYSTEM_SIDE
from quintet.trading.models import ReconciledTradeState, RiskExposure, Side, TradeKey


@dataclass(frozen=True)
class RiskMetadata:
    """Contract fields required to calculate open risk."""

    multiplier: float
    price_magnifier: int = 1


def build_risk_exposures(
    state: ReconciledTradeState,
    *,
    current_prices: Mapping[TradeKey, float],
    metadata: Mapping[TradeKey, RiskMetadata],
) -> list[RiskExposure]:
    """Build side-aware exposures for positions with known stops and prices."""
    exposures: list[RiskExposure] = []
    for key, position in state.positions_by_key.items():
        stop = state.protective_stops_by_key.get(key)
        if stop is None or stop.aux_price is None:
            raise ValueError(
                f"{position.local_symbol} is reconciled as open but has no stop price"
            )
        if key not in current_prices:
            raise ValueError(f"Missing current price for {position.local_symbol} {key}")
        if key not in metadata:
            raise ValueError(f"Missing risk metadata for {position.local_symbol} {key}")

        system = key[1]
        risk_meta = metadata[key]
        exposures.append(
            RiskExposure(
                con_id=position.con_id,
                system=system,
                side=Side.from_config(SYSTEM_SIDE[system]),
                quantity=position.quantity,
                current_price=current_prices[key],
                stop_price=stop.aux_price,
                multiplier=risk_meta.multiplier,
                price_magnifier=risk_meta.price_magnifier,
            )
        )
    return exposures
