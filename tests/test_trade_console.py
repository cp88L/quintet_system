from datetime import datetime
from pathlib import Path
from unittest import TestCase

from quintet.broker.models import (
    AccountState,
    BrokerError,
    BrokerOrder,
    BrokerPosition,
    BrokerState,
)
from quintet.execution.models import (
    AlertLevel,
    AlertIntent,
    ExecutionEvent,
    ExecutionReport,
    ExecutionStatus,
    ModifyOrderIntent,
    PlaceBracketIntent,
)
from quintet.execution.serialize import to_plain
from quintet.run.console import format_trade_report
from quintet.trading.models import Side, SignalCandidate, TradePlan


class TradeConsoleTests(TestCase):
    def test_format_trade_report_lists_actionable_brackets(self) -> None:
        signal = SignalCandidate(
            system="C4",
            side=Side.LONG,
            symbol="PA",
            local_symbol="PAM6",
            con_id=642484759,
            exchange="NYMEX",
            currency="USD",
            multiplier=100.0,
            min_tick=0.5,
            price_magnifier=1,
            entry_price=1622.5,
            stop_price=1315.0,
            prob=0.305837,
            tau=0.271505,
            cluster_id=2,
        )
        intent = PlaceBracketIntent(
            key=signal.key,
            side=Side.LONG,
            symbol="PA",
            local_symbol="PAM6",
            exchange="NYMEX",
            currency="USD",
            quantity=1,
            entry_action="BUY",
            entry_order_type="STP LMT",
            entry_stop_price=1622.5,
            entry_limit_price=1622.5,
            protective_action="SELL",
            protective_order_type="STP LMT",
            protective_stop_price=1315.0,
            protective_limit_price=1315.0,
            risk_per_contract=30750.0,
            total_risk=30750.0,
        )
        report = ExecutionReport(
            generated_at=datetime(2026, 4, 30, 15, 15),
            mode="dry_run",
            submitted=[
                {
                    "status": ExecutionStatus.DRY_RUN.value,
                    "intent": to_plain(intent),
                }
            ],
        )

        lines = format_trade_report(
            broker_state=_broker_state(),
            plan=TradePlan(signals=[signal], intents=[intent]),
            report=report,
            report_dir=Path("/tmp/reports"),
        )
        output = "\n".join(lines)

        self.assertIn("State: flat; no classified positions or orders", output)
        self.assertIn("1 actionable signal(s) (C4=1)", output)
        self.assertIn("New entries (dry run - no orders submitted", output)
        self.assertIn("PAM6", output)
        self.assertNotIn("0.3058", output)
        self.assertNotIn("0.2715", output)
        self.assertNotIn("cl=2", output)
        self.assertIn("$30,750", output)
        self.assertIn("dry run only", output)
        self.assertIn("Skipped signals: none", output)
        self.assertIn("Alerts: none", output)

    def test_format_trade_report_surfaces_state_skips_alerts_and_events(self) -> None:
        order = BrokerOrder(
            order_id=77,
            con_id=100,
            symbol="ES",
            local_symbol="ESM6",
            action="SELL",
            order_type="STP",
            quantity=1,
            status="Submitted",
            system="E4",
            aux_price=5100.0,
        )
        broker_state = _broker_state(
            positions=[
                BrokerPosition(
                    account="DU123",
                    con_id=100,
                    symbol="ES",
                    local_symbol="ESM6",
                    quantity=1,
                    avg_cost=5200.0,
                )
            ],
            open_orders=[order],
            recent_errors=[
                BrokerError(
                    request_id=-1,
                    code=2104,
                    message="Market data farm connection is OK",
                    timestamp=datetime(2026, 4, 30, 15, 15),
                )
            ],
        )
        modify = ModifyOrderIntent(
            order_id=77,
            key=(100, "E4"),
            aux_price=5110.0,
            reason="position_stop_level_changed",
        )
        alert = AlertIntent(
            code="external_order",
            message="Manual order needs review",
            key=(100, "E4"),
            level=AlertLevel.WARNING,
            operator_action="Review in Gateway",
        )
        report = ExecutionReport(
            generated_at=datetime(2026, 4, 30, 15, 15),
            mode="live",
            submitted=[
                {
                    "status": ExecutionStatus.MODIFIED.value,
                    "order_id": 77,
                    "intent": to_plain(modify),
                }
            ],
            skipped=[
                {"key": [100, "E4"], "symbol": "ES", "local_symbol": "ESM6", "reason": "already_has_position"}
            ],
            alerts=[to_plain(alert)],
            events=[
                ExecutionEvent(
                    status=ExecutionStatus.MODIFIED,
                    intent="ModifyOrderIntent",
                    order_id=77,
                    key=(100, "E4"),
                    message="accepted",
                )
            ],
        )

        output = "\n".join(
            format_trade_report(
                broker_state=broker_state,
                plan=TradePlan(intents=[modify, alert], skipped=report.skipped),
                report=report,
                report_dir=Path("/tmp/reports"),
            )
        )

        self.assertIn("Open positions:", output)
        self.assertIn("Open orders:", output)
        self.assertIn("IBKR warnings/errors:", output)
        self.assertIn("2104", output)
        self.assertNotIn("BrokerErrorSeverity", output)
        self.assertIn("Maintenance actions:", output)
        self.assertIn("modify_order", output)
        self.assertIn("Skipped signals:", output)
        self.assertIn("already_has_position", output)
        self.assertIn("Alerts:", output)
        self.assertIn("external_order", output)
        self.assertIn("Execution events:", output)
        self.assertIn("accepted", output)


def _broker_state(
    *,
    positions: list[BrokerPosition] | None = None,
    open_orders: list[BrokerOrder] | None = None,
    recent_errors: list[BrokerError] | None = None,
) -> BrokerState:
    return BrokerState(
        collected_at=datetime(2026, 4, 30, 15, 15),
        account=AccountState(net_liquidation=3779187.71),
        positions=positions or [],
        open_orders=open_orders or [],
        recent_errors=recent_errors or [],
    )
