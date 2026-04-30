from datetime import datetime
from unittest import TestCase

from quintet.broker.models import AccountState, BrokerOrder, BrokerPosition, BrokerState
from quintet.execution.models import AlertIntent, CancelOrderIntent, ModifyOrderIntent
from quintet.trading.maintain import plan_maintenance
from quintet.trading.models import RiskState, SignalCandidate, Side
from quintet.trading.planner import build_trade_plan
from quintet.trading.reconcile import reconcile_state


def _broker_state(
    *,
    positions: list[BrokerPosition] | None = None,
    open_orders: list[BrokerOrder] | None = None,
) -> BrokerState:
    return BrokerState(
        collected_at=datetime(2026, 1, 1, 12, 0),
        account=AccountState(net_liquidation=100_000.0),
        positions=positions or [],
        open_orders=open_orders or [],
    )


def _signal(
    *,
    con_id: int = 100,
    system: str = "C4",
    side: Side = Side.LONG,
    entry_price: float = 100.0,
    stop_price: float = 95.0,
) -> SignalCandidate:
    return SignalCandidate(
        system=system,
        side=side,
        symbol="ES",
        local_symbol="ESH6",
        con_id=con_id,
        exchange="CME",
        currency="USD",
        multiplier=50.0,
        min_tick=0.25,
        price_magnifier=1,
        entry_price=entry_price,
        stop_price=stop_price,
    )


def _order(
    *,
    order_id: int = 1,
    con_id: int = 100,
    system: str | None = "C4",
    action: str = "BUY",
    order_type: str = "STP LMT",
    aux_price: float | None = 100.0,
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
        currency="USD",
        system=system,
        aux_price=aux_price,
        limit_price=aux_price,
        parent_id=parent_id,
    )


def _position(*, con_id: int = 100, quantity: float = 1.0) -> BrokerPosition:
    return BrokerPosition(
        account="DU123",
        con_id=con_id,
        symbol="ES",
        local_symbol="ESH6",
        quantity=quantity,
        avg_cost=100.0,
    )


def _plan_from_broker_state(
    state: BrokerState,
    *,
    signals: list[SignalCandidate] | None = None,
):
    reconciled = reconcile_state(state)
    maintenance = plan_maintenance(reconciled, today=None)
    return build_trade_plan(
        signals=signals or [],
        state=reconciled,
        maintenance=maintenance,
        risk_state=RiskState(net_liquidation=state.account.net_liquidation),
    )


class BrokerStateScenarioTests(TestCase):
    def test_stale_entry_order_from_broker_state_is_cancelled(self) -> None:
        state = _broker_state(open_orders=[_order(order_id=11)])

        plan = _plan_from_broker_state(state)

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, CancelOrderIntent)
        self.assertEqual(intent.order_id, 11)
        self.assertEqual(intent.reason, "signal_disappeared")

    def test_changed_entry_order_from_broker_state_is_modified(self) -> None:
        signal = _signal(entry_price=101.0)
        state = _broker_state(open_orders=[_order(order_id=12, aux_price=100.0)])

        plan = _plan_from_broker_state(state, signals=[signal])

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, ModifyOrderIntent)
        self.assertEqual(intent.order_id, 12)
        self.assertEqual(intent.aux_price, 101.0)
        self.assertEqual(intent.reason, "entry_level_changed")

    def test_changed_position_stop_from_broker_state_is_modified(self) -> None:
        signal = _signal(stop_price=96.0)
        state = _broker_state(
            positions=[_position()],
            open_orders=[
                _order(
                    order_id=13,
                    action="SELL",
                    order_type="STP LMT",
                    aux_price=95.0,
                )
            ],
        )

        plan = _plan_from_broker_state(state, signals=[signal])

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, ModifyOrderIntent)
        self.assertEqual(intent.order_id, 13)
        self.assertEqual(intent.aux_price, 96.0)
        self.assertEqual(intent.reason, "position_stop_level_changed")
        self.assertEqual(plan.skipped[0]["reason"], "already_has_position")

    def test_broker_position_without_stop_reports_missing_stop_alert(self) -> None:
        state = _broker_state(positions=[_position()])

        plan = _plan_from_broker_state(state)

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, AlertIntent)
        self.assertEqual(intent.code, "missing_protective_stop")

    def test_manual_order_without_system_reports_external_order_alert(self) -> None:
        state = _broker_state(
            open_orders=[
                _order(
                    order_id=14,
                    system=None,
                    action="BUY",
                    order_type="LMT",
                    aux_price=None,
                )
            ]
        )

        plan = _plan_from_broker_state(state)

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, AlertIntent)
        self.assertEqual(intent.code, "external_or_unclassified_order")
