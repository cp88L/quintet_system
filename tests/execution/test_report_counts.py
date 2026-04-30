import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from quintet.execution.models import (
    ExecutionEvent,
    ExecutionReport,
    ExecutionStatus,
)
from quintet.state.stores import ReportStore


class ExecutionReportCountsTests(TestCase):
    def test_counts_separate_operator_outcomes(self) -> None:
        report = ExecutionReport(
            generated_at=datetime(2026, 1, 1, 12, 0),
            mode="live",
            submitted=[
                {"status": ExecutionStatus.SUBMITTED.value, "intent": {}},
                {"status": ExecutionStatus.EXIT_SUBMITTED.value, "intent": {}},
                {"status": ExecutionStatus.CANCEL_REQUESTED.value, "intent": {}},
                {"status": ExecutionStatus.MODIFIED.value, "intent": {}},
            ],
            skipped=[{"reason": "risk"}],
            alerts=[{"code": "missing_stop"}],
            events=[
                ExecutionEvent(
                    status=ExecutionStatus.REPORTED,
                    intent="RollEntryIntent",
                ),
                ExecutionEvent(
                    status=ExecutionStatus.PLACE_THREW,
                    intent="PlaceBracketIntent",
                    message="boom",
                ),
                ExecutionEvent(
                    status=ExecutionStatus.CANCEL_THREW,
                    intent="CancelOrderIntent",
                    message="boom",
                ),
            ],
        )

        self.assertEqual(report.counts.submitted, 2)
        self.assertEqual(report.counts.cancel_requested, 1)
        self.assertEqual(report.counts.modified, 1)
        self.assertEqual(report.counts.reported_only, 1)
        self.assertEqual(report.counts.alerts, 1)
        self.assertEqual(report.counts.threw, 2)
        self.assertEqual(report.counts.skipped, 1)

    def test_report_store_writes_counts_to_json(self) -> None:
        report = ExecutionReport(
            generated_at=datetime(2026, 1, 1, 12, 0),
            mode="dry_run",
            submitted=[
                {"status": ExecutionStatus.DRY_RUN.value, "intent": {}},
            ],
            alerts=[{"code": "external_order"}],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = ReportStore(Path(tmpdir)).write_execution_report(report)
            data = json.loads(path.read_text())

        self.assertEqual(
            data["counts"],
            {
                "submitted": 0,
                "cancel_requested": 0,
                "modified": 0,
                "reported_only": 0,
                "alerts": 1,
                "threw": 0,
                "dry_run": 1,
                "skipped": 0,
            },
        )
