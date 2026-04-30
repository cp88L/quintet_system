from unittest import TestCase

from quintet.execution.dry_run import DryRunExecutor
from quintet.execution.models import (
    LastDayCloseoutIntent,
    ProtectiveStopSnapshot,
    RollEntryIntent,
)
from quintet.trading.models import Side, TradePlan


class DryRunExecutorTests(TestCase):
    def test_last_day_roll_records_operator_summary(self) -> None:
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

        report = DryRunExecutor().execute(TradePlan(intents=[intent]))

        self.assertEqual(
            report.submitted[0]["roll_summary"],
            {
                "old_contract": "ESH6",
                "new_contract": "ESM6",
                "quantity": 1,
                "rspos": 0.90,
                "threshold": 0.85,
                "protective_stop_price": 97.0,
            },
        )
