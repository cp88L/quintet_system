from datetime import date
from unittest import TestCase

from quintet.broker.models import BrokerOrder, BrokerPosition, ContractMeta
from quintet.execution.models import AlertIntent, LastDayCloseoutIntent
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


def _stop() -> BrokerOrder:
    return BrokerOrder(
        order_id=7,
        con_id=100,
        symbol="ES",
        local_symbol="ESH6",
        action="SELL",
        order_type="STP LMT",
        quantity=2,
        status="Submitted",
        exchange="CME",
        currency="USD",
        system="E4",
        aux_price=95.0,
        limit_price=94.75,
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
    def test_next_rth_on_last_day_generates_exit_intent_day_before(self) -> None:
        state = ReconciledTradeState(
            positions_by_key={(100, "E4"): _position()},
            protective_stops_by_key={(100, "E4"): _stop()},
        )

        plan = plan_maintenance(
            state,
            today=date(2026, 6, 18),
            contract_meta={100: _meta(last_day=date(2026, 6, 19))},
            next_rth_days={100: date(2026, 6, 19)},
        )

        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertIsInstance(intent, LastDayCloseoutIntent)
        self.assertEqual(intent.side, Side.LONG)
        self.assertEqual(intent.quantity, 2)
        self.assertEqual(intent.exchange, "CME")
        self.assertEqual(intent.reason, "last_day")
        self.assertEqual(intent.protective_stop.order_id, 7)
        self.assertEqual(intent.protective_stop.aux_price, 95.0)
        self.assertEqual(intent.oca_group, "ROLL_100_E4_20260619")

    def test_next_rth_before_last_day_does_not_exit(self) -> None:
        state = ReconciledTradeState(
            positions_by_key={(100, "E4"): _position()},
            protective_stops_by_key={(100, "E4"): _stop()},
        )

        plan = plan_maintenance(
            state,
            today=date(2026, 6, 18),
            contract_meta={100: _meta(last_day=date(2026, 6, 19))},
            next_rth_days={100: date(2026, 6, 18)},
        )

        self.assertEqual(plan.intents, [])

    def test_missing_last_day_metadata_alerts_instead_of_guessing(self) -> None:
        state = ReconciledTradeState(positions_by_key={(100, "E4"): _position()})

        plan = plan_maintenance(
            state,
            today=date(2026, 6, 18),
            next_rth_days={100: date(2026, 6, 19)},
        )

        self.assertEqual(len(plan.intents), 1)
        alert = plan.intents[0]
        self.assertIsInstance(alert, AlertIntent)
        self.assertEqual(alert.code, "missing_last_day_metadata")

    def test_missing_next_rth_day_alerts_instead_of_guessing(self) -> None:
        state = ReconciledTradeState(
            positions_by_key={(100, "E4"): _position()},
            protective_stops_by_key={(100, "E4"): _stop()},
        )

        plan = plan_maintenance(
            state,
            today=date(2026, 6, 18),
            contract_meta={100: _meta(last_day=date(2026, 6, 19))},
        )

        self.assertEqual(len(plan.intents), 1)
        alert = plan.intents[0]
        self.assertIsInstance(alert, AlertIntent)
        self.assertEqual(alert.code, "missing_next_rth_day")
