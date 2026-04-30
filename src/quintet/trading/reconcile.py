"""Classify broker state into trade-planning buckets."""

from __future__ import annotations

from collections import defaultdict

from quintet.broker.models import BrokerOrder, BrokerState
from quintet.config import SYSTEM_SIDE
from quintet.trading.models import ReconciledTradeState, Side, TradeKey


ENTRY_TYPES = {"STP LMT", "MKT"}
STOP_TYPES = {"STP", "STP LMT"}


def reconcile_state(state: BrokerState) -> ReconciledTradeState:
    """Classify open positions/orders by `(con_id, system)`.

    Positions are attributed from standalone protective stops with a system.
    Unknown positions remain report-only per the v1 spec.
    """
    entry_orders: dict[TradeKey, BrokerOrder] = {}
    protective_stops: dict[TradeKey, BrokerOrder] = {}
    orphaned: list[BrokerOrder] = []
    external: list[BrokerOrder] = []
    classified_order_ids: set[int] = set()

    position_conids = {p.con_id for p in state.positions}
    child_orders_by_parent: dict[int, list[BrokerOrder]] = defaultdict(list)
    for order in state.open_orders:
        if order.parent_id is not None:
            child_orders_by_parent[order.parent_id].append(order)

    for order in state.open_orders:
        if order.order_id in classified_order_ids:
            continue
        if order.system is None:
            external.append(order)
            continue
        if order.system not in SYSTEM_SIDE:
            external.append(order)
            continue
        side = Side.from_config(SYSTEM_SIDE[order.system])
        key = (order.con_id, order.system)
        if _is_entry_order(order, side):
            entry_orders[key] = order
            classified_order_ids.add(order.order_id)
            for child in child_orders_by_parent.get(order.order_id, []):
                protective_stops[key] = child
                classified_order_ids.add(child.order_id)
        elif _is_protective_order(order, side):
            if order.parent_id is not None:
                protective_stops[key] = order
                classified_order_ids.add(order.order_id)
            elif order.con_id in position_conids:
                protective_stops[key] = order
                classified_order_ids.add(order.order_id)
            else:
                orphaned.append(order)
                classified_order_ids.add(order.order_id)
        else:
            external.append(order)

    positions_by_key = {}
    positions_without_stop = []
    unknown_positions = []
    stops_by_conid = defaultdict(list)
    for key, stop in protective_stops.items():
        stops_by_conid[stop.con_id].append((key, stop))

    for position in state.positions:
        matches = stops_by_conid.get(position.con_id, [])
        if len(matches) == 1:
            positions_by_key[matches[0][0]] = position
        elif not matches:
            positions_without_stop.append(position)
        else:
            unknown_positions.append(position)

    return ReconciledTradeState(
        positions_by_key=positions_by_key,
        entry_orders_by_key=entry_orders,
        protective_stops_by_key=protective_stops,
        orphaned_orders=orphaned,
        positions_without_protective_stop=positions_without_stop,
        unknown_system_positions=unknown_positions,
        external_or_unclassified_orders=external,
    )


def _is_entry_order(order: BrokerOrder, side: Side) -> bool:
    return order.action == side.entry_action and order.order_type in ENTRY_TYPES


def _is_protective_order(order: BrokerOrder, side: Side) -> bool:
    return order.action == side.protective_action and order.order_type in STOP_TYPES
