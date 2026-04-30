from datetime import date
from unittest import TestCase

from quintet.broker.models import BrokerPosition, ContractMeta
from quintet.execution.models import AlertIntent, ExitPositionIntent
from quintet.trading.maintain import plan_maintenance
from quintet.trading.models import ReconciledTradeState, Side


def _position() -> BrokerPosition:
    return BrokerPosition(
        account="DU123",
        con_id=100,
        symbol="ES",
        local_symbol="ESH6",
        quantity=2,
        avg_cost=100.0,
    )


def _meta(*, last_day: date | None) -> ContractMeta:
    return ContractMeta(
        con_id=100,
        symbol="ES",
        local_symbol="ESH6",
        exchange="CME",
        currency="USD",
        multiplier=50.0,
        min_tick=0.25,
        last_day=last_day,
    )


class MaintenanceTests(TestCase):
    def test_last_day_position_generates_exit_intent(self) -> None:
        state = ReconciledTradeState(positions_by_key={(100, "E4"): _position()})

        plan = plan_maintenance(
            state,
            today=date(2026, 6, 19),
            contract_meta={100: _meta(last_day=date(2026, 6, 19))},
        )

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, ExitPositionIntent)
        self.assertEqual(intent.side, Side.LONG)
        self.assertEqual(intent.quantity, 2)
        self.assertEqual(intent.exchange, "CME")
        self.assertEqual(intent.reason, "last_day")

    def test_before_last_day_does_not_exit(self) -> None:
        state = ReconciledTradeState(positions_by_key={(100, "E4"): _position()})

        plan = plan_maintenance(
            state,
            today=date(2026, 6, 18),
            contract_meta={100: _meta(last_day=date(2026, 6, 19))},
        )

        self.assertEqual(plan.intents, [])

    def test_missing_last_day_metadata_alerts_instead_of_guessing(self) -> None:
        state = ReconciledTradeState(positions_by_key={(100, "E4"): _position()})

        plan = plan_maintenance(state, today=date(2026, 6, 19))

        self.assertEqual(len(plan.intents), 1)
        alert = plan.intents[0]
        self.assertIsInstance(alert, AlertIntent)
        self.assertEqual(alert.code, "missing_last_day_metadata")
