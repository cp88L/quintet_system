from unittest import TestCase

from quintet import config
from quintet.broker.ibkr import state


class IbkrClientConfigTests(TestCase):
    def test_broker_state_uses_client_zero_for_manual_order_visibility(self) -> None:
        self.assertEqual(config.CLIENT_ID, 0)

    def test_broker_state_fails_fast_if_client_zero_is_changed(self) -> None:
        original = config.CLIENT_ID
        try:
            config.CLIENT_ID = 7
            with self.assertRaisesRegex(ValueError, "requires config.CLIENT_ID = 0"):
                state._require_client_zero()
        finally:
            config.CLIENT_ID = original
