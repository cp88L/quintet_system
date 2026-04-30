"""Map IBKR callback objects into broker-neutral models."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from quintet.broker.models import AccountState, BrokerOrder, BrokerPosition
from quintet.config import VOICE_TO_SYSTEM


def map_position(account: str, contract, quantity, avg_cost) -> BrokerPosition:
    """Map an IBKR position callback into a broker-neutral position."""
    return BrokerPosition(
        account=account,
        con_id=int(_get(contract, "conId", 0) or 0),
        symbol=str(_get(contract, "symbol", "") or ""),
        local_symbol=str(_get(contract, "localSymbol", "") or ""),
        quantity=float(quantity),
        avg_cost=float(avg_cost),
    )


def map_open_order(order_id: int, contract, order, order_state) -> BrokerOrder:
    """Map an IBKR open-order callback into a broker-neutral order."""
    order_ref = str(_get(order, "orderRef", "") or "")
    parent_id = int(_get(order, "parentId", 0) or 0)
    return BrokerOrder(
        order_id=int(order_id),
        con_id=int(_get(contract, "conId", 0) or 0),
        symbol=str(_get(contract, "symbol", "") or ""),
        local_symbol=str(_get(contract, "localSymbol", "") or ""),
        exchange=str(_get(contract, "exchange", "") or ""),
        action=str(_get(order, "action", "") or ""),
        order_type=str(_get(order, "orderType", "") or ""),
        quantity=int(float(_get(order, "totalQuantity", 0) or 0)),
        status=str(_get(order_state, "status", "") or "Unknown"),
        currency=str(_get(contract, "currency", "") or ""),
        system=VOICE_TO_SYSTEM.get(order_ref),
        aux_price=_optional_float(_get(order, "auxPrice", None)),
        limit_price=_optional_float(_get(order, "lmtPrice", None)),
        parent_id=parent_id or None,
        perm_id=_optional_int(_get(order, "permId", None)),
        oca_group=str(_get(order, "ocaGroup", "") or "") or None,
        oca_type=_optional_int(_get(order, "ocaType", None)),
        order_ref=order_ref or None,
        tif=str(_get(order, "tif", "") or "") or None,
        outside_rth=_optional_bool(_get(order, "outsideRth", None)),
        transmit=_optional_bool(_get(order, "transmit", None)),
    )


def map_account_summary(rows: Iterable[Mapping[str, str]]) -> AccountState:
    """Map IBKR account summary rows into the account subset needed by planning."""
    rows = list(rows)
    net_liquidation_row = _first_row(rows, "NetLiquidation")
    if net_liquidation_row is None:
        raise ValueError("IBKR account summary did not include NetLiquidation")

    buying_power_row = _first_row(rows, "BuyingPower")
    account = net_liquidation_row.get("account") or None
    currency = net_liquidation_row.get("currency") or "USD"
    return AccountState(
        account_id=account,
        currency=currency,
        net_liquidation=float(net_liquidation_row["value"]),
        buying_power=(
            float(buying_power_row["value"]) if buying_power_row is not None else None
        ),
        raw_values={
            _raw_key(row): _optional_number(row.get("value", ""))
            for row in rows
        },
    )


def _first_row(rows: list[Mapping[str, str]], tag: str) -> Mapping[str, str] | None:
    return next((row for row in rows if row.get("tag") == tag), None)


def _raw_key(row: Mapping[str, str]) -> str:
    account = row.get("account") or ""
    tag = row.get("tag") or ""
    currency = row.get("currency") or ""
    return ".".join(part for part in [account, tag, currency] if part)


def _optional_number(value: str) -> str | float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number < 1e300 else None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _get(obj, name: str, default=None):
    return getattr(obj, name, default) if obj is not None else default
