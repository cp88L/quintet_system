from unittest import TestCase

from quintet.broker.models import BrokerOrder
from quintet.execution.ibkr import IbkrExecutor
from quintet.execution.models import (
    CancelOrderIntent,
    ExecutionStatus,
    ExitPositionIntent,
    ModifyOrderIntent,
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
