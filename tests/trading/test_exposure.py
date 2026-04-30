from unittest import TestCase

from quintet.broker.models import BrokerOrder, BrokerPosition
from quintet.trading.exposure import RiskMetadata, build_risk_exposures
from quintet.trading.models import ReconciledTradeState, Side


class ExposureTests(TestCase):
    def test_builds_side_aware_risk_exposure_from_position_stop_and_price(self) -> None:
        key = (100, "C4")
        state = ReconciledTradeState(
            positions_by_key={
                key: BrokerPosition(
                    account="DU123",
                    con_id=100,
                    symbol="ES",
                    local_symbol="ESH6",
                    quantity=2,
                    avg_cost=100.0,
                )
            },
            protective_stops_by_key={
                key: BrokerOrder(
                    order_id=7,
                    con_id=100,
                    symbol="ES",
                    local_symbol="ESH6",
                    action="SELL",
                    order_type="STP LMT",
                    quantity=2,
                    status="Submitted",
                    aux_price=95.0,
                )
            },
        )

        exposures = build_risk_exposures(
            state,
            current_prices={key: 100.0},
            metadata={key: RiskMetadata(multiplier=50.0)},
        )

        self.assertEqual(len(exposures), 1)
        self.assertEqual(exposures[0].side, Side.LONG)
        self.assertEqual(exposures[0].current_price, 100.0)
        self.assertEqual(exposures[0].stop_price, 95.0)
        self.assertEqual(exposures[0].multiplier, 50.0)

    def test_missing_stop_price_fails_fast(self) -> None:
        key = (100, "C4")
        state = ReconciledTradeState(
            positions_by_key={
                key: BrokerPosition(
                    account="DU123",
                    con_id=100,
                    symbol="ES",
                    local_symbol="ESH6",
                    quantity=1,
                    avg_cost=100.0,
                )
            },
            protective_stops_by_key={
                key: BrokerOrder(
                    order_id=7,
                    con_id=100,
                    symbol="ES",
                    local_symbol="ESH6",
                    action="SELL",
                    order_type="STP LMT",
                    quantity=1,
                    status="Submitted",
                )
            },
        )

        with self.assertRaisesRegex(ValueError, "no stop price"):
            build_risk_exposures(
                state,
                current_prices={key: 100.0},
                metadata={key: RiskMetadata(multiplier=50.0)},
            )
