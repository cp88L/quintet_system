from unittest import TestCase

from quintet.broker.ibkr.orders import (
    build_bracket_order_requests,
    build_exit_order_request,
    build_modify_order_request,
)
from quintet.broker.models import BrokerOrder
from quintet.execution.models import (
    ExitPositionIntent,
    ModifyOrderIntent,
    PlaceBracketIntent,
)
from quintet.trading.models import Side


def _intent(*, side: Side, system: str) -> PlaceBracketIntent:
    return PlaceBracketIntent(
        key=(100, system),
        side=side,
        symbol="ES",
        local_symbol="ESH6",
        exchange="CME",
        currency="USD",
        quantity=3,
        entry_action=side.entry_action,
        entry_order_type="STP LMT",
        entry_stop_price=100.0 if side is Side.LONG else 95.0,
        entry_limit_price=100.0 if side is Side.LONG else 95.0,
        protective_action=side.protective_action,
        protective_order_type="STP LMT",
        protective_stop_price=95.0 if side is Side.LONG else 100.0,
        protective_limit_price=95.0 if side is Side.LONG else 100.0,
        risk_per_contract=250.0,
        total_risk=750.0,
    )


class IbkrOrderTests(TestCase):
    def test_long_bracket_uses_parent_child_transmit_and_voice_ref(self) -> None:
        requests = build_bracket_order_requests(
            _intent(side=Side.LONG, system="C4"),
            entry_order_id=11,
            stop_order_id=12,
        )

        entry = requests[0].order
        stop = requests[1].order

        self.assertEqual(requests[0].contract.conId, 100)
        self.assertEqual(requests[0].contract.localSymbol, "ESH6")
        self.assertEqual(entry.action, "BUY")
        self.assertEqual(entry.orderType, "STP LMT")
        self.assertEqual(entry.auxPrice, 100.0)
        self.assertEqual(entry.lmtPrice, 100.0)
        self.assertFalse(entry.transmit)
        self.assertEqual(entry.orderRef, "trumpet")
        self.assertEqual(stop.action, "SELL")
        self.assertEqual(stop.parentId, 11)
        self.assertTrue(stop.transmit)
        self.assertEqual(stop.orderRef, "trumpet")

    def test_short_bracket_flips_entry_and_protective_actions(self) -> None:
        requests = build_bracket_order_requests(
            _intent(side=Side.SHORT, system="CS4"),
            entry_order_id=21,
            stop_order_id=22,
        )

        entry = requests[0].order
        stop = requests[1].order

        self.assertEqual(entry.action, "SELL")
        self.assertEqual(entry.auxPrice, 95.0)
        self.assertEqual(entry.orderRef, "tenor")
        self.assertEqual(stop.action, "BUY")
        self.assertEqual(stop.auxPrice, 100.0)
        self.assertEqual(stop.parentId, 21)
        self.assertEqual(stop.orderRef, "tenor")

    def test_modify_reuses_current_order_shape_with_new_prices(self) -> None:
        request = build_modify_order_request(
            BrokerOrder(
                order_id=31,
                con_id=100,
                symbol="ES",
                local_symbol="ESH6",
                action="BUY",
                order_type="STP LMT",
                quantity=3,
                status="Submitted",
                exchange="CME",
                currency="USD",
                system="E4",
                aux_price=100.0,
                limit_price=100.0,
                parent_id=11,
                order_ref="piano",
                tif="GTC",
                outside_rth=True,
                transmit=True,
            ),
            ModifyOrderIntent(
                order_id=31,
                key=(100, "E4"),
                aux_price=101.0,
                limit_price=101.0,
            ),
        )

        self.assertEqual(request.order_id, 31)
        self.assertEqual(request.contract.conId, 100)
        self.assertEqual(request.contract.localSymbol, "ESH6")
        self.assertEqual(request.order.action, "BUY")
        self.assertEqual(request.order.orderType, "STP LMT")
        self.assertEqual(request.order.totalQuantity, 3)
        self.assertEqual(request.order.auxPrice, 101.0)
        self.assertEqual(request.order.lmtPrice, 101.0)
        self.assertEqual(request.order.parentId, 11)
        self.assertEqual(request.order.orderRef, "piano")
        self.assertTrue(request.order.transmit)

    def test_exit_builds_market_order_with_side_aware_action(self) -> None:
        request = build_exit_order_request(
            ExitPositionIntent(
                key=(100, "C4"),
                side=Side.LONG,
                symbol="ES",
                local_symbol="ESH6",
                quantity=2,
                exchange="CME",
                currency="USD",
            ),
            order_id=41,
        )

        self.assertEqual(request.order_id, 41)
        self.assertEqual(request.contract.conId, 100)
        self.assertEqual(request.contract.localSymbol, "ESH6")
        self.assertEqual(request.order.action, "SELL")
        self.assertEqual(request.order.orderType, "MKT")
        self.assertEqual(request.order.totalQuantity, 2)
        self.assertEqual(request.order.orderRef, "trumpet")
        self.assertTrue(request.order.transmit)
