"""Signal-independent maintenance planning."""

from __future__ import annotations

from quintet.execution.models import AlertIntent, CancelOrderIntent
from quintet.trading.models import MaintenancePlan, ReconciledTradeState


def plan_maintenance(state: ReconciledTradeState) -> MaintenancePlan:
    """Plan simple report/cancel intents that do not depend on today's signal."""
    intents: list[object] = []
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
                message=f"{position.local_symbol} has a broker position with no stop",
                key=None,
            )
        )
    for position in state.unknown_system_positions:
        intents.append(
            AlertIntent(
                code="unknown_system_position",
                message=(
                    f"{position.local_symbol} has broker position "
                    "with no unique system attribution"
                ),
                key=None,
            )
        )
    for order in state.external_or_unclassified_orders:
        intents.append(
            AlertIntent(
                code="external_or_unclassified_order",
                message=f"Order {order.order_id} on {order.local_symbol} is unclassified",
                key=(order.con_id, order.system) if order.system else None,
            )
        )
    return MaintenancePlan(intents=intents)
