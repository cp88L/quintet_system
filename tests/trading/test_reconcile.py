from datetime import datetime, timezone
from unittest import TestCase

from quintet.broker.models import AccountState, BrokerOrder, BrokerPosition, BrokerState
from quintet.execution.models import AlertIntent
from quintet.trading.maintain import plan_maintenance
from quintet.trading.reconcile import reconcile_state


def _state(*, positions=None, orders=None) -> BrokerState:
    return BrokerState(
        collected_at=datetime(2026, 4, 30, tzinfo=timezone.utc),
        account=AccountState(net_liquidation=100_000.0),
        positions=list(positions or []),
        open_orders=list(orders or []),
    )


def _position(con_id: int = 100, quantity: int = 1) -> BrokerPosition:
    return BrokerPosition(
        account="DU123",
        con_id=con_id,
        symbol="ES",
        local_symbol="ESH6",
        quantity=quantity,
        avg_cost=100.0,
    )


def _order(
    *,
    order_id: int,
    con_id: int = 100,
    system: str | None = "C4",
    action: str = "BUY",
    order_type: str = "STP LMT",
    parent_id: int | None = None,
) -> BrokerOrder:
    return BrokerOrder(
        order_id=order_id,
        con_id=con_id,
        symbol="ES",
        local_symbol="ESH6",
        action=action,
        order_type=order_type,
        quantity=1,
        status="Submitted",
        exchange="CME",
        system=system,
        parent_id=parent_id,
    )


class ReconcileTests(TestCase):
    def test_parent_entry_classifies_child_stop_without_external_alert(self) -> None:
        entry = _order(order_id=1, action="BUY", system="C4")
        child_stop = _order(
            order_id=2,
            action="SELL",
            system=None,
            parent_id=1,
        )

        reconciled = reconcile_state(_state(orders=[entry, child_stop]))

        self.assertIs(reconciled.entry_orders_by_key[(100, "C4")], entry)
        self.assertIs(reconciled.protective_stops_by_key[(100, "C4")], child_stop)
        self.assertEqual(reconciled.external_or_unclassified_orders, [])

    def test_short_system_uses_sell_entry_and_buy_stop(self) -> None:
        entry = _order(order_id=1, system="CS4", action="SELL")
        child_stop = _order(
            order_id=2,
            system=None,
            action="BUY",
            parent_id=1,
        )

        reconciled = reconcile_state(_state(orders=[entry, child_stop]))

        self.assertIs(reconciled.entry_orders_by_key[(100, "CS4")], entry)
        self.assertIs(reconciled.protective_stops_by_key[(100, "CS4")], child_stop)

    def test_standalone_stop_attributes_existing_position(self) -> None:
        position = _position()
        stop = _order(order_id=3, action="SELL", system="C4")

        reconciled = reconcile_state(_state(positions=[position], orders=[stop]))

        self.assertIs(reconciled.positions_by_key[(100, "C4")], position)
        self.assertIs(reconciled.protective_stops_by_key[(100, "C4")], stop)
        self.assertEqual(reconciled.positions_without_protective_stop, [])

    def test_missing_stop_is_report_only_alert(self) -> None:
        position = _position()

        reconciled = reconcile_state(_state(positions=[position]))
        maintenance = plan_maintenance(reconciled)

        self.assertEqual(reconciled.positions_without_protective_stop, [position])
        self.assertEqual(len(maintenance.intents), 1)
        alert = maintenance.intents[0]
        self.assertIsInstance(alert, AlertIntent)
        self.assertEqual(alert.code, "missing_protective_stop")

    def test_multiple_matching_stops_leave_position_unknown(self) -> None:
        position = _position()
        c4_stop = _order(order_id=3, action="SELL", system="C4")
        e4_stop = _order(order_id=4, action="SELL", system="E4")

        reconciled = reconcile_state(_state(positions=[position], orders=[c4_stop, e4_stop]))

        self.assertEqual(reconciled.positions_by_key, {})
        self.assertEqual(reconciled.unknown_system_positions, [position])
