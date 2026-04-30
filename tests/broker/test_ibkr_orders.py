from unittest import TestCase

from quintet.broker.ibkr.orders import (
    build_bracket_order_requests,
    build_exit_order_request,
    build_last_day_closeout_order_requests,
    build_modify_order_request,
    build_roll_entry_order_requests,
)
from quintet.broker.models import BrokerOrder
from quintet.execution.models import (
    ExitPositionIntent,
    LastDayCloseoutIntent,
    ModifyOrderIntent,
    PlaceBracketIntent,
    ProtectiveStopSnapshot,
    RollEntryIntent,
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


def _closeout_intent(*, side: Side = Side.LONG) -> LastDayCloseoutIntent:
    return LastDayCloseoutIntent(
        key=(100, "E4"),
        side=side,
        symbol="ES",
        local_symbol="ESH6",
        quantity=2,
        exchange="CME",
        currency="USD",
        protective_stop=ProtectiveStopSnapshot(
            order_id=7,
            order_type="STP LMT",
            aux_price=95.0 if side is Side.LONG else 105.0,
            limit_price=94.75 if side is Side.LONG else 105.25,
        ),
        oca_group="ROLL_100_E4_20260430",
    )


def _roll_entry_intent(*, side: Side = Side.LONG) -> RollEntryIntent:
    return RollEntryIntent(
        old_key=(100, "E4"),
        new_key=(200, "E4"),
        side=side,
        symbol="ES",
        old_local_symbol="ESH6",
        new_local_symbol="ESM6",
        exchange="CME",
        currency="USD",
        quantity=2,
        rspos=0.90,
        threshold=0.85,
        protective_stop_price=97.0 if side is Side.LONG else 103.0,
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

    def test_last_day_closeout_builds_replacement_stop_oca_pair(self) -> None:
        requests = build_last_day_closeout_order_requests(
            _closeout_intent(),
            replacement_stop_order_id=51,
            market_exit_order_id=52,
        )

        replacement = requests[0].order
        exit_order = requests[1].order

        self.assertEqual(requests[0].contract.conId, 100)
        self.assertEqual(requests[0].contract.localSymbol, "ESH6")
        self.assertEqual(replacement.action, "SELL")
        self.assertEqual(replacement.orderType, "STP LMT")
        self.assertEqual(replacement.totalQuantity, 2)
        self.assertEqual(replacement.auxPrice, 95.0)
        self.assertEqual(replacement.lmtPrice, 94.75)
        self.assertEqual(replacement.parentId, 0)
        self.assertEqual(replacement.ocaGroup, "ROLL_100_E4_20260430")
        self.assertEqual(replacement.ocaType, 1)
        self.assertFalse(replacement.transmit)
        self.assertTrue(replacement.outsideRth)
        self.assertEqual(replacement.orderRef, "piano")
        self.assertEqual(exit_order.action, "SELL")
        self.assertEqual(exit_order.orderType, "MKT")
        self.assertEqual(exit_order.totalQuantity, 2)
        self.assertEqual(exit_order.ocaGroup, "ROLL_100_E4_20260430")
        self.assertEqual(exit_order.ocaType, 1)
        self.assertTrue(exit_order.transmit)
        self.assertFalse(exit_order.outsideRth)
        self.assertEqual(exit_order.orderRef, "piano")

    def test_short_last_day_closeout_flips_replacement_stop_and_exit(self) -> None:
        requests = build_last_day_closeout_order_requests(
            _closeout_intent(side=Side.SHORT),
            replacement_stop_order_id=61,
            market_exit_order_id=62,
        )

        self.assertEqual(requests[0].order.action, "BUY")
        self.assertEqual(requests[0].order.auxPrice, 105.0)
        self.assertEqual(requests[0].order.lmtPrice, 105.25)
        self.assertEqual(requests[1].order.action, "BUY")

    def test_roll_entry_builds_rth_market_parent_and_eth_stop_child(self) -> None:
        requests = build_roll_entry_order_requests(
            _roll_entry_intent(),
            parent_order_id=71,
            stop_order_id=72,
        )

        parent = requests[0].order
        stop = requests[1].order

        self.assertEqual(requests[0].contract.conId, 200)
        self.assertEqual(requests[0].contract.localSymbol, "ESM6")
        self.assertEqual(parent.action, "BUY")
        self.assertEqual(parent.orderType, "MKT")
        self.assertEqual(parent.totalQuantity, 2)
        self.assertFalse(parent.transmit)
        self.assertFalse(parent.outsideRth)
        self.assertEqual(parent.orderRef, "piano")
        self.assertEqual(stop.action, "SELL")
        self.assertEqual(stop.orderType, "STP")
        self.assertEqual(stop.totalQuantity, 2)
        self.assertEqual(stop.auxPrice, 97.0)
        self.assertEqual(stop.parentId, 71)
        self.assertTrue(stop.transmit)
        self.assertTrue(stop.outsideRth)
        self.assertEqual(stop.orderRef, "piano")
