import json
import importlib
import tempfile
from pathlib import Path
from unittest import TestCase

import dash

from quintet.dashboard.app import create_app
from quintet.dashboard.data import loader
from quintet.data.paths import DataPaths


class TradeReportsDashboardTests(TestCase):
    def test_trade_reports_page_is_registered(self) -> None:
        create_app()

        paths = {page["path"] for page in dash.page_registry.values()}
        self.assertIn("/trade", paths)

    def test_latest_trade_report_loader_reads_report_files(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))
                report_dir = loader._paths.base / "reports"
                report_dir.mkdir(parents=True)
                (report_dir / "latest_trade_plan.json").write_text(
                    json.dumps(
                        {"signals": [], "intents": [{"reason": "last_day_roll"}]}
                    )
                )
                (report_dir / "latest_execution_report.json").write_text(
                    json.dumps({"mode": "live", "counts": {"reported_only": 1}})
                )

                plan = loader.load_latest_trade_plan()
                report = loader.load_latest_execution_report()
        finally:
            loader._paths = old_paths

        self.assertEqual(plan["intents"][0]["reason"], "last_day_roll")
        self.assertEqual(report["counts"]["reported_only"], 1)

    def test_roll_submitted_record_formats_operator_details(self) -> None:
        create_app()
        trade_reports = importlib.import_module("quintet.dashboard.pages.trade_reports")
        record = {
            "cancelled_stop_order_id": 189,
            "closeout_order_ids": [190, 191],
            "roll_order_ids": [192, 193],
            "roll_summary": {
                "old_contract": "ESM6",
                "new_contract": "ESU6",
                "quantity": 1,
                "rspos": 0.9,
                "threshold": 0.85,
                "protective_stop_price": 6931.75,
            },
        }

        self.assertEqual(
            trade_reports._format_order_ids(record),
            "cancel 189; closeout 190, 191; roll 192, 193",
        )
        self.assertEqual(
            trade_reports._submitted_contract(record, {}),
            "ESM6 -> ESU6",
        )
        self.assertEqual(
            trade_reports._submitted_roll_details(record),
            "qty 1 | RSpos 0.9000 | threshold 0.8500 | stop 6931.7500",
        )
