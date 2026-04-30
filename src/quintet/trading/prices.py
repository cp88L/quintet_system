"""Price helpers for order planning."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

_ROUNDING_MODES = {
    "nearest": ROUND_HALF_UP,
    "up": ROUND_CEILING,
    "down": ROUND_FLOOR,
}


def round_to_tick(price: float, min_tick: float, mode: str = "nearest") -> float:
    """Round a price to a valid tick using decimal arithmetic."""
    if min_tick <= 0:
        raise ValueError("min_tick must be positive")
    if mode not in _ROUNDING_MODES:
        raise ValueError(f"unsupported rounding mode: {mode}")

    price_dec = Decimal(str(price))
    tick_dec = Decimal(str(min_tick))
    ticks = (price_dec / tick_dec).to_integral_value(rounding=_ROUNDING_MODES[mode])
    return float(ticks * tick_dec)
