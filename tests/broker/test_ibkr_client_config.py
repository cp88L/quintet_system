from unittest import TestCase

from quintet import config
from quintet.broker.ibkr import state


class IbkrClientConfigTests(TestCase):
    def test_broker_state_uses_client_zero_for_manual_order_visibility(self) -> None:
        self.assertEqual(config.CLIENT_ID, 0)

    def test_state_client_binds_manual_orders_with_client_zero(self) -> None:
        client = RecordingStateClient()

        client.connect_and_run()

        self.assertEqual(client.connected_args, (config.HOST, config.PORT, 0))
        self.assertTrue(client.auto_open_orders)
        self.assertEqual(client.get_next_order_id(), 1)

    def test_broker_state_fails_fast_if_client_zero_is_changed(self) -> None:
        original = config.CLIENT_ID
        try:
            config.CLIENT_ID = 7
            with self.assertRaisesRegex(ValueError, "requires config.CLIENT_ID = 0"):
                state._require_client_zero()
        finally:
            config.CLIENT_ID = original


class RecordingStateClient(state.IbkrStateClient):
    def __init__(self) -> None:
        super().__init__()
        self.connected_args: tuple[str, int, int] | None = None
        self.auto_open_orders: bool | None = None

    def connect(self, host: str, port: int, clientId: int) -> None:
        self.connected_args = (host, port, clientId)

    def isConnected(self) -> bool:
        return True

    def _run_loop(self) -> None:
        self.nextValidId(1)

    def reqAutoOpenOrders(self, autoBind: bool) -> None:
        self.auto_open_orders = autoBind
