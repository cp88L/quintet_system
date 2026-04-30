"""Signal-independent maintenance planning."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from quintet.broker.models import ContractMeta
from quintet.config import SYSTEM_SIDE
from quintet.execution.models import AlertIntent, CancelOrderIntent, ExitPositionIntent
from quintet.trading.models import MaintenancePlan, ReconciledTradeState, Side


def plan_maintenance(
    state: ReconciledTradeState,
    *,
    today: date | None = None,
    contract_meta: Mapping[int, ContractMeta] | None = None,
) -> MaintenancePlan:
    """Plan simple report/cancel intents that do not depend on today's signal."""
    intents: list[object] = []
    contract_meta = contract_meta or {}
    for key, position in state.positions_by_key.items():
        if today is None:
            continue
        meta = contract_meta.get(position.con_id)
        if meta is None or meta.last_day is None:
            intents.append(
                AlertIntent(
                    code="missing_last_day_metadata",
                    message=(
                        f"{position.local_symbol} has no last-day metadata "
                        "for maintenance exit planning"
                    ),
                    key=key,
                    operator_action=(
                        "Fix contract metadata before relying on last-day exits."
                    ),
                )
            )
            continue
        if today >= meta.last_day:
            intents.append(
                ExitPositionIntent(
                    key=key,
                    side=Side.from_config(SYSTEM_SIDE[key[1]]),
                    symbol=position.symbol,
                    local_symbol=position.local_symbol,
                    quantity=int(abs(position.quantity)),
                    exchange=meta.exchange,
                    currency=meta.currency,
                    reason="last_day",
                )
            )
    for order in state.orphaned_orders:
        intents.append(
            CancelOrderIntent(
                order_id=order.order_id,
                key=(order.con_id, order.system) if order.system else None,
                reason="orphaned_stop",
            )
        )
    for position in state.positions_without_protective_stop:
        intents.append(
            AlertIntent(
                code="missing_protective_stop",
                message=(
                    f"{position.local_symbol} broker position has no protective "
                    f"stop: account={position.account}, con_id={position.con_id}, "
                    f"quantity={position.quantity:g}. No order was sent."
                ),
                key=None,
                operator_action=(
                    "Verify or place the protective stop manually before the next run."
                ),
            )
        )
    for position in state.unknown_system_positions:
        intents.append(
            AlertIntent(
                code="unknown_system_position",
                message=(
                    f"{position.local_symbol} has broker position "
                    "with no unique system attribution. No order was sent."
                ),
                key=None,
                operator_action=(
                    "Review manual position attribution and protective stops."
                ),
            )
        )
    for order in state.external_or_unclassified_orders:
        intents.append(
            AlertIntent(
                code="external_or_unclassified_order",
                message=(
                    f"Order {order.order_id} on {order.local_symbol} is outside "
                    f"system management: action={order.action}, "
                    f"type={order.order_type}, quantity={order.quantity}, "
                    f"status={order.status}. No order was sent."
                ),
                key=(order.con_id, order.system) if order.system else None,
                operator_action="Review the outside order manually.",
            )
        )
    return MaintenancePlan(intents=intents)
