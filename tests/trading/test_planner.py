from unittest import TestCase

from quintet.broker.models import BrokerOrder, BrokerPosition
from quintet.execution.models import CancelOrderIntent, ModifyOrderIntent, PlaceBracketIntent
from quintet.trading.models import (
    MaintenancePlan,
    ReconciledTradeState,
    RiskState,
    Side,
    SignalCandidate,
)
from quintet.trading.planner import build_trade_plan


def _signal(*, system: str = "C4", side: Side = Side.LONG) -> SignalCandidate:
    return SignalCandidate(
        system=system,
        side=side,
        symbol="ES",
        local_symbol="ESH6",
        con_id=100,
        exchange="CME",
        currency="USD",
        multiplier=50.0,
        min_tick=0.25,
        price_magnifier=1,
        entry_price=100.0 if side is Side.LONG else 95.0,
        stop_price=95.0 if side is Side.LONG else 100.0,
    )


def _order(
    *,
    order_id: int = 1,
    system: str = "C4",
    action: str = "BUY",
    order_type: str = "STP LMT",
    aux_price: float | None = 100.0,
) -> BrokerOrder:
    return BrokerOrder(
        order_id=order_id,
        con_id=100,
        symbol="ES",
        local_symbol="ESH6",
        action=action,
        order_type=order_type,
        quantity=1,
        status="Submitted",
        exchange="CME",
        system=system,
        aux_price=aux_price,
    )


def _position() -> BrokerPosition:
    return BrokerPosition(
        account="DU123",
        con_id=100,
        symbol="ES",
        local_symbol="ESH6",
        quantity=1,
        avg_cost=100.0,
    )


def _plan(signal: SignalCandidate, state: ReconciledTradeState | None = None):
    return build_trade_plan(
        signals=[signal],
        state=state or ReconciledTradeState(),
        maintenance=MaintenancePlan(),
        risk_state=RiskState(net_liquidation=100_000.0),
    )


class PlannerTests(TestCase):
    def test_places_long_bracket_with_side_aware_actions(self) -> None:
        plan = _plan(_signal())

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, PlaceBracketIntent)
        self.assertEqual(intent.entry_action, "BUY")
        self.assertEqual(intent.protective_action, "SELL")
        self.assertEqual(intent.entry_order_type, "STP LMT")
        self.assertEqual(intent.protective_order_type, "STP LMT")
        self.assertEqual(intent.quantity, 3)

    def test_places_short_bracket_with_side_aware_actions(self) -> None:
        signal = _signal(system="CS4", side=Side.SHORT)
        plan = _plan(signal)

        intent = plan.intents[0]
        self.assertIsInstance(intent, PlaceBracketIntent)
        self.assertEqual(intent.entry_action, "SELL")
        self.assertEqual(intent.protective_action, "BUY")
        self.assertEqual(intent.quantity, 3)

    def test_existing_entry_skips_duplicate_bracket(self) -> None:
        signal = _signal()
        state = ReconciledTradeState(entry_orders_by_key={signal.key: _order()})

        plan = _plan(signal, state)

        self.assertEqual(plan.intents, [])
        self.assertEqual(plan.skipped[0]["reason"], "already_has_entry_order")

    def test_stale_entry_is_cancelled_when_signal_disappears(self) -> None:
        signal = _signal()
        state = ReconciledTradeState(entry_orders_by_key={signal.key: _order()})

        plan = build_trade_plan(
            signals=[],
            state=state,
            maintenance=MaintenancePlan(),
            risk_state=RiskState(net_liquidation=100_000.0),
        )

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, CancelOrderIntent)
        self.assertEqual(intent.reason, "signal_disappeared")

    def test_position_stop_is_modified_on_tick_rounded_change(self) -> None:
        signal = _signal()
        stop = _order(order_id=7, action="SELL", aux_price=94.75)
        state = ReconciledTradeState(
            positions_by_key={signal.key: _position()},
            protective_stops_by_key={signal.key: stop},
        )

        plan = _plan(signal, state)

        self.assertIsInstance(plan.intents[0], ModifyOrderIntent)
        self.assertEqual(plan.intents[0].order_id, 7)
        self.assertEqual(plan.intents[0].aux_price, 95.0)
        self.assertEqual(plan.skipped[0]["reason"], "already_has_position")
