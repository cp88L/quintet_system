import json
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
