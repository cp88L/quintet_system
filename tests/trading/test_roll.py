from unittest import TestCase

from quintet.execution.models import AlertIntent, ExitPositionIntent, RollEntryIntent
from quintet.trading.models import Side
from quintet.trading.roll import RollCandidate, plan_roll_entries


def _exit_intent(*, system: str = "E4") -> ExitPositionIntent:
    return ExitPositionIntent(
        key=(100, system),
        side=Side.LONG,
        symbol="ES",
        local_symbol="ESH6",
        quantity=2,
        exchange="CME",
        currency="USD",
        reason="last_day",
    )


def _candidate(*, rspos: float | None = 0.90, con_id: int = 200) -> RollCandidate:
    return RollCandidate(
        system="E4",
        side=Side.LONG,
        symbol="ES",
        local_symbol="ESM6",
        con_id=con_id,
        exchange="CME",
        currency="USD",
        rspos=rspos,
        stop_price=95.0,
    )


class RollTests(TestCase):
    def test_roll_enabled_system_with_rspos_above_threshold_reports_roll_entry(self) -> None:
        intents = plan_roll_entries(
            [_exit_intent()],
            {("E4", "ES"): _candidate(rspos=0.90)},
        )

        self.assertEqual(len(intents), 1)
        intent = intents[0]
        self.assertIsInstance(intent, RollEntryIntent)
        self.assertEqual(intent.old_key, (100, "E4"))
        self.assertEqual(intent.new_key, (200, "E4"))
        self.assertEqual(intent.quantity, 2)
        self.assertEqual(intent.protective_stop_price, 95.0)

    def test_roll_below_threshold_reports_info_alert(self) -> None:
        intents = plan_roll_entries(
            [_exit_intent()],
            {("E4", "ES"): _candidate(rspos=0.80)},
        )

        self.assertEqual(len(intents), 1)
        alert = intents[0]
        self.assertIsInstance(alert, AlertIntent)
        self.assertEqual(alert.code, "roll_not_eligible")
        self.assertEqual(alert.level.value, "info")

    def test_commodities_do_not_roll(self) -> None:
        intents = plan_roll_entries(
            [_exit_intent(system="C4")],
            {("C4", "ES"): _candidate(rspos=0.90)},
        )

        self.assertEqual(intents, [])
