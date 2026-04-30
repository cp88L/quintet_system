from unittest import TestCase

from quintet.broker.models import BrokerOrder
from quintet.execution.ibkr import IbkrExecutor
from quintet.execution.models import (
    CancelOrderIntent,
    ExecutionStatus,
    ExitPositionIntent,
    LastDayCloseoutIntent,
    ModifyOrderIntent,
    ProtectiveStopSnapshot,
    RollEntryIntent,
)
from quintet.trading.models import Side, TradePlan


class RecordingClient:
    def __init__(self) -> None:
        self.cancelled: list[int] = []
        self.placed: list[tuple[int, object, object]] = []
        self.open_orders: list[BrokerOrder] = []
        self.next_order_id = 900

    def cancel_order(self, order_id: int) -> None:
        self.cancelled.append(order_id)

    def place_order(self, order_id: int, contract, order) -> None:
        self.placed.append((order_id, contract, order))

    def get_open_orders(self) -> list:
        return list(self.open_orders)

    def get_next_order_id(self) -> int:
        order_id = self.next_order_id
        self.next_order_id += 1
        return order_id


class IbkrExecutorTests(TestCase):
    def test_cancel_intent_sends_cancel_request_and_records_event(self) -> None:
        client = RecordingClient()
        intent = CancelOrderIntent(order_id=123, key=(100, "C4"), reason="stale")

        report = IbkrExecutor().execute_connected(
            TradePlan(intents=[intent]),
            client,
        )

        self.assertEqual(client.cancelled, [123])
        self.assertEqual(report.submitted[0]["status"], "cancel_requested")
        self.assertEqual(report.events[0].status, ExecutionStatus.CANCEL_REQUESTED)
        self.assertEqual(report.events[0].order_id, 123)

    def test_modify_intent_sends_same_id_place_order_and_records_event(self) -> None:
        client = RecordingClient()
        client.open_orders = [
            BrokerOrder(
                order_id=123,
                con_id=100,
                symbol="ES",
                local_symbol="ESH6",
                action="BUY",
                order_type="STP LMT",
                quantity=1,
                status="Submitted",
                exchange="CME",
                currency="USD",
                aux_price=100.0,
                limit_price=100.0,
                tif="GTC",
                outside_rth=True,
            )
        ]
        intent = ModifyOrderIntent(
            order_id=123,
            key=(100, "C4"),
            aux_price=101.0,
            limit_price=101.0,
        )

        report = IbkrExecutor().execute_connected(
            TradePlan(intents=[intent]),
            client,
        )

        self.assertEqual(len(client.placed), 1)
        self.assertEqual(client.placed[0][0], 123)
        self.assertEqual(client.placed[0][2].auxPrice, 101.0)
        self.assertEqual(report.submitted[0]["status"], "modified")
        self.assertEqual(report.events[0].status, ExecutionStatus.MODIFIED)

    def test_exit_intent_sends_market_exit_and_records_event(self) -> None:
        client = RecordingClient()
        intent = ExitPositionIntent(
            key=(100, "C4"),
            side=Side.LONG,
            symbol="ES",
            local_symbol="ESH6",
            quantity=1,
            exchange="CME",
            currency="USD",
            reason="last_day",
        )

        report = IbkrExecutor().execute_connected(
            TradePlan(intents=[intent]),
            client,
        )

        self.assertEqual(len(client.placed), 1)
        self.assertEqual(client.placed[0][0], 900)
        self.assertEqual(client.placed[0][2].action, "SELL")
        self.assertEqual(client.placed[0][2].orderType, "MKT")
        self.assertEqual(report.submitted[0]["status"], "exit_submitted")
        self.assertEqual(report.events[0].status, ExecutionStatus.EXIT_SUBMITTED)

    def test_last_day_closeout_submits_oca_closeout_and_roll_bracket(self) -> None:
        client = RecordingClient()
        intent = LastDayCloseoutIntent(
            key=(100, "E4"),
            side=Side.LONG,
            symbol="ES",
            local_symbol="ESH6",
            quantity=1,
            exchange="CME",
            currency="USD",
            protective_stop=ProtectiveStopSnapshot(
                order_id=77,
                order_type="STP LMT",
                aux_price=95.0,
                limit_price=94.75,
            ),
            oca_group="ROLL_100_E4_20260430",
            roll_entry=RollEntryIntent(
                old_key=(100, "E4"),
                new_key=(200, "E4"),
                side=Side.LONG,
                symbol="ES",
                old_local_symbol="ESH6",
                new_local_symbol="ESM6",
                exchange="CME",
                currency="USD",
                quantity=1,
                rspos=0.90,
                threshold=0.85,
                protective_stop_price=97.0,
            ),
        )

        report = IbkrExecutor().execute_connected(
            TradePlan(intents=[intent]),
            client,
        )

        self.assertEqual(client.cancelled, [77])
        self.assertEqual(
            [order_id for order_id, _, _ in client.placed],
            [900, 901, 902, 903],
        )
        replacement = client.placed[0][2]
        closeout = client.placed[1][2]
        roll_parent = client.placed[2][2]
        roll_stop = client.placed[3][2]
        self.assertEqual(replacement.orderType, "STP LMT")
        self.assertEqual(replacement.ocaGroup, "ROLL_100_E4_20260430")
        self.assertFalse(replacement.transmit)
        self.assertTrue(replacement.outsideRth)
        self.assertEqual(closeout.orderType, "MKT")
        self.assertEqual(closeout.ocaGroup, "ROLL_100_E4_20260430")
        self.assertTrue(closeout.transmit)
        self.assertFalse(closeout.outsideRth)
        self.assertEqual(roll_parent.orderType, "MKT")
        self.assertFalse(roll_parent.transmit)
        self.assertFalse(roll_parent.outsideRth)
        self.assertEqual(roll_stop.orderType, "STP")
        self.assertEqual(roll_stop.parentId, 902)
        self.assertTrue(roll_stop.transmit)
        self.assertTrue(roll_stop.outsideRth)
        self.assertEqual(report.submitted[0]["status"], "roll_submitted")
        self.assertEqual(report.submitted[0]["cancelled_stop_order_id"], 77)
        self.assertEqual(report.submitted[0]["closeout_order_ids"], [900, 901])
        self.assertEqual(report.submitted[0]["roll_order_ids"], [902, 903])
        self.assertEqual(report.counts.roll_submitted, 1)
        self.assertEqual(report.events[0].status, ExecutionStatus.CANCEL_REQUESTED)
        self.assertEqual(report.events[1].status, ExecutionStatus.ROLL_SUBMITTED)
