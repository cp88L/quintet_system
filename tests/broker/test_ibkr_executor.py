from unittest import TestCase

from quintet.execution.ibkr import IbkrExecutor
from quintet.execution.models import CancelOrderIntent, ExecutionStatus
from quintet.trading.models import TradePlan


class RecordingClient:
    def __init__(self) -> None:
        self.cancelled: list[int] = []

    def cancel_order(self, order_id: int) -> None:
        self.cancelled.append(order_id)

    def get_open_orders(self) -> list:
        return []


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
