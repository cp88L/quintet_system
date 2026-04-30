from unittest import TestCase

from quintet.broker.ibkr.orders import build_bracket_order_requests
from quintet.execution.models import PlaceBracketIntent
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
