from unittest import TestCase

from quintet.trading.prices import round_to_tick


class PriceTests(TestCase):
    def test_round_to_tick_uses_decimal_half_up(self) -> None:
        self.assertEqual(round_to_tick(100.12, 0.25), 100.0)
        self.assertEqual(round_to_tick(100.13, 0.25), 100.25)
        self.assertEqual(round_to_tick(100.125, 0.25), 100.25)
        self.assertEqual(round_to_tick(1.235, 0.01), 1.24)

    def test_round_to_tick_supports_directional_modes(self) -> None:
        self.assertEqual(round_to_tick(100.12, 0.25, mode="up"), 100.25)
        self.assertEqual(round_to_tick(100.12, 0.25, mode="down"), 100.0)

    def test_round_to_tick_rejects_bad_tick(self) -> None:
        with self.assertRaises(ValueError):
            round_to_tick(100.0, 0.0)
