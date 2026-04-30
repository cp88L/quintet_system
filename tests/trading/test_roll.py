from unittest import TestCase

from quintet.execution.models import (
    AlertIntent,
    LastDayCloseoutIntent,
    ProtectiveStopSnapshot,
    RollEntryIntent,
)
from quintet.trading.models import Side
from quintet.trading.roll import RollCandidate, plan_roll_entries


def _closeout_intent(*, system: str = "E4") -> LastDayCloseoutIntent:
    return LastDayCloseoutIntent(
        key=(100, system),
        side=Side.LONG,
        symbol="ES",
        local_symbol="ESH6",
        quantity=2,
        exchange="CME",
        currency="USD",
        protective_stop=ProtectiveStopSnapshot(
            order_id=7,
            order_type="STP LMT",
            aux_price=95.0,
            limit_price=94.75,
        ),
        oca_group=f"ROLL_100_{system}_20260430",
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
            [_closeout_intent()],
            {("E4", "ES"): _candidate(rspos=0.90)},
        )

        self.assertEqual(len(intents), 1)
        intent = intents[0]
        self.assertIsInstance(intent, LastDayCloseoutIntent)
        self.assertIsInstance(intent.roll_entry, RollEntryIntent)
        self.assertEqual(intent.roll_entry.old_key, (100, "E4"))
        self.assertEqual(intent.roll_entry.new_key, (200, "E4"))
        self.assertEqual(intent.roll_entry.quantity, 2)
        self.assertEqual(intent.roll_entry.protective_stop_price, 95.0)

    def test_roll_below_threshold_reports_info_alert(self) -> None:
        intents = plan_roll_entries(
            [_closeout_intent()],
            {("E4", "ES"): _candidate(rspos=0.80)},
        )

        self.assertEqual(len(intents), 2)
        self.assertIsInstance(intents[0], LastDayCloseoutIntent)
        alert = intents[1]
        self.assertIsInstance(alert, AlertIntent)
        self.assertEqual(alert.code, "roll_not_eligible")
        self.assertEqual(alert.level.value, "info")

    def test_commodities_do_not_roll(self) -> None:
        intents = plan_roll_entries(
            [_closeout_intent(system="C4")],
            {("C4", "ES"): _candidate(rspos=0.90)},
        )

        self.assertEqual(len(intents), 1)
        self.assertIsInstance(intents[0], LastDayCloseoutIntent)
        self.assertIsNone(intents[0].roll_entry)

    def test_missing_roll_candidate_keeps_closeout_and_alerts(self) -> None:
        intents = plan_roll_entries([_closeout_intent()], {})

        self.assertEqual(len(intents), 2)
        self.assertIsInstance(intents[0], LastDayCloseoutIntent)
        self.assertIsNone(intents[0].roll_entry)
        self.assertIsInstance(intents[1], AlertIntent)
        self.assertEqual(intents[1].code, "roll_candidate_missing")

    def test_same_contract_candidate_keeps_closeout_and_alerts(self) -> None:
        intents = plan_roll_entries(
            [_closeout_intent()],
            {("E4", "ES"): _candidate(con_id=100)},
        )

        self.assertEqual(len(intents), 2)
        self.assertIsInstance(intents[0], LastDayCloseoutIntent)
        self.assertIsNone(intents[0].roll_entry)
        self.assertIsInstance(intents[1], AlertIntent)
        self.assertEqual(intents[1].code, "roll_contract_not_advanced")

    def test_missing_rspos_keeps_closeout_and_alerts(self) -> None:
        intents = plan_roll_entries(
            [_closeout_intent()],
            {("E4", "ES"): _candidate(rspos=None)},
        )

        self.assertEqual(len(intents), 2)
        self.assertIsInstance(intents[0], LastDayCloseoutIntent)
        self.assertIsNone(intents[0].roll_entry)
        self.assertIsInstance(intents[1], AlertIntent)
        self.assertEqual(intents[1].code, "roll_rspos_missing")

    def test_missing_stop_keeps_closeout_and_alerts(self) -> None:
        candidate = _candidate()
        candidate = RollCandidate(
            system=candidate.system,
            side=candidate.side,
            symbol=candidate.symbol,
            local_symbol=candidate.local_symbol,
            con_id=candidate.con_id,
            exchange=candidate.exchange,
            currency=candidate.currency,
            rspos=candidate.rspos,
            stop_price=None,
        )

        intents = plan_roll_entries(
            [_closeout_intent()],
            {("E4", "ES"): candidate},
        )

        self.assertEqual(len(intents), 2)
        self.assertIsInstance(intents[0], LastDayCloseoutIntent)
        self.assertIsNone(intents[0].roll_entry)
        self.assertIsInstance(intents[1], AlertIntent)
        self.assertEqual(intents[1].code, "roll_stop_missing")
