from unittest import TestCase

from quintet.trading.models import RiskExposure, Side
from quintet.trading.risk import (
    calculate_contract_risk,
    calculate_portfolio_risk,
    calculate_position_risk,
    calculate_position_size,
    calculate_risk_budget,
)


class RiskTests(TestCase):
    def test_calculate_position_size_floors_budget_to_whole_contracts(self) -> None:
        self.assertEqual(calculate_contract_risk(100.0, 95.0, multiplier=50.0), 250.0)
        self.assertEqual(
            calculate_position_size(1_000.0, 100.0, 95.0, multiplier=50.0),
            4,
        )
        self.assertEqual(
            calculate_position_size(249.99, 100.0, 95.0, multiplier=50.0),
            0,
        )

    def test_position_risk_is_side_aware(self) -> None:
        self.assertEqual(
            calculate_position_risk(
                Side.LONG,
                current_price=100.0,
                stop_price=95.0,
                quantity=2,
                multiplier=50.0,
            ),
            500.0,
        )
        self.assertEqual(
            calculate_position_risk(
                Side.SHORT,
                current_price=80.0,
                stop_price=85.0,
                quantity=3,
                multiplier=100.0,
            ),
            1_500.0,
        )

    def test_position_risk_never_increases_free_equity(self) -> None:
        self.assertEqual(calculate_position_risk(Side.LONG, 100.0, 101.0, 1, 50.0), 0.0)
        self.assertEqual(calculate_position_risk(Side.SHORT, 100.0, 99.0, 1, 50.0), 0.0)

    def test_risk_budget_uses_one_pooled_equity_bucket(self) -> None:
        positions = [
            RiskExposure(
                con_id=1,
                system="C4",
                side=Side.LONG,
                quantity=2,
                current_price=100.0,
                stop_price=95.0,
                multiplier=50.0,
            ),
            RiskExposure(
                con_id=2,
                system="CS4",
                side=Side.SHORT,
                quantity=3,
                current_price=80.0,
                stop_price=85.0,
                multiplier=100.0,
            ),
        ]

        risk_state = calculate_risk_budget(
            account_equity=100_000.0,
            positions=positions,
            heat_by_system={"C4": 0.01, "CS4": 0.02},
        )

        self.assertEqual(calculate_portfolio_risk(positions), 2_000.0)
        self.assertEqual(risk_state.portfolio_risk, 2_000.0)
        self.assertEqual(risk_state.free_equity, 98_000.0)
        self.assertEqual(
            risk_state.risk_budget_by_system,
            {"C4": 980.0, "CS4": 1_960.0},
        )

    def test_negative_free_equity_collapses_budgets_to_zero(self) -> None:
        risk_state = calculate_risk_budget(
            account_equity=100.0,
            positions=[
                RiskExposure(
                    con_id=1,
                    system="C4",
                    side=Side.LONG,
                    quantity=1,
                    current_price=100.0,
                    stop_price=0.0,
                    multiplier=50.0,
                )
            ],
            heat_by_system={"C4": 0.01},
        )

        self.assertLess(risk_state.free_equity, 0)
        self.assertEqual(risk_state.risk_budget_by_system, {"C4": 0.0})

    def test_risk_rejects_invalid_multiplier(self) -> None:
        with self.assertRaises(ValueError):
            calculate_position_size(100.0, 100.0, 95.0, multiplier=0.0)
