import importlib
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase

import dash

from quintet.dashboard.app import create_app
from quintet.dashboard.data import loader
from quintet.data.paths import DataPaths


class OverviewDashboardTests(TestCase):
    def test_overview_page_is_registered_at_root(self) -> None:
        create_app()

        paths = {page["path"] for page in dash.page_registry.values()}
        self.assertIn("/", paths)

    def test_overview_layout_summarizes_snapshot_attention(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))
                _write_reports(loader._paths)
                _write_product_master(loader._paths)

                create_app()
                overview = importlib.import_module("quintet.dashboard.pages.overview")
                children = overview.layout()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        text = _component_text(children)
        self.assertIn("Overview", text)
        self.assertIn("$100,000", text)
        self.assertIn("Total", text)
        self.assertIn("+$1,750", text)
        self.assertIn("$6,000", text)
        self.assertNotIn("Total Return", text)
        self.assertNotIn("Total Risk", text)
        self.assertIn("Needs Attention", text)
        self.assertIn("MISSING_STOP_TEST", text)
        self.assertIn("PAM6", text)
        self.assertIn("#88", text)
        self.assertIn("Current Position Stops", text)
        self.assertIn("Old Position Stops", text)
        self.assertIn("Latest Run", text)
        self.assertIn("Planned actions", text)
        self.assertIn("Orders sent", text)
        self.assertIn("Execution errors", text)

    def test_empty_overview_uses_snapshot_missing_message(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))

                create_app()
                overview = importlib.import_module("quintet.dashboard.pages.overview")
                children = overview.layout()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        self.assertIn("No trade-flow snapshot found", _component_text(children))


def _write_reports(paths: DataPaths) -> None:
    report_dir = paths.base / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest_trade_plan.json").write_text(
        json.dumps(
            {
                "generated_at": datetime(2026, 4, 30, 16, 28).isoformat(),
                "signals": [{"key": [100, "E4"]}],
                "intents": [{"reason": "new_signal"}],
                "skipped": [{"symbol": "GC", "reason": "risk_budget"}],
            }
        )
    )
    (report_dir / "latest_execution_report.json").write_text(
        json.dumps(
            {
                "generated_at": datetime(2026, 4, 30, 16, 30).isoformat(),
                "mode": "dry_run",
                "counts": {
                    "submitted": 1,
                    "alerts": 1,
                    "dry_run": 1,
                    "skipped": 1,
                },
                "alerts": [
                    {
                        "level": "warning",
                        "code": "MISSING_STOP_TEST",
                        "message": "Synthetic missing stop alert.",
                        "operator_action": "Check the stop.",
                    }
                ],
                "broker_state": {
                    "collected_at": datetime(2026, 4, 30, 16, 29).isoformat(),
                    "account": {
                        "net_liquidation": 100000.0,
                        "currency": "USD",
                        "buying_power": 50000.0,
                    },
                    "positions": [
                        {
                            "account": "DU123",
                            "con_id": 100,
                            "symbol": "ES",
                            "local_symbol": "ESM6",
                            "quantity": 1,
                            "avg_cost": 260000.0,
                            "market_price": 5220.0,
                        },
                        {
                            "account": "DU123",
                            "con_id": 200,
                            "symbol": "PA",
                            "local_symbol": "PAM6",
                            "quantity": 1,
                            "avg_cost": 162250.0,
                            "market_price": 1630.0,
                        },
                    ],
                    "open_orders": [
                        {
                            "order_id": 77,
                            "con_id": 100,
                            "symbol": "ES",
                            "local_symbol": "ESM6",
                            "action": "SELL",
                            "order_type": "STP LMT",
                            "quantity": 1,
                            "status": "Submitted",
                            "system": "E4",
                            "aux_price": 5100.0,
                            "limit_price": 5099.0,
                        },
                        {
                            "order_id": 88,
                            "con_id": 300,
                            "symbol": "NQ",
                            "local_symbol": "NQM6",
                            "action": "SELL",
                            "order_type": "STP LMT",
                            "quantity": 1,
                            "status": "Submitted",
                            "system": "E4",
                            "aux_price": 19000.0,
                        },
                    ],
                    "recent_fills": [],
                    "next_rth_days": {},
                    "contract_meta": {},
                },
            }
        )
    )


def _write_product_master(paths: DataPaths) -> None:
    paths.reference.mkdir(parents=True, exist_ok=True)
    paths.product_master_csv.write_text(
        "\n".join(
            [
                "symbol,active,multiplier,priceMagnifier,longName,c4,cs4,e4,e7,e13",
                "ES,1,50,1,E-mini S&P 500,0,0,1,1,1",
                "PA,1,100,1,Palladium,1,1,0,0,0",
            ]
        )
    )


def _component_text(component) -> str:
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    if isinstance(component, (list, tuple)):
        return " ".join(_component_text(child) for child in component)
    children = getattr(component, "children", None)
    return _component_text(children)
