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


class FillsDashboardTests(TestCase):
    def test_fills_page_is_registered(self) -> None:
        create_app()

        paths = {page["path"] for page in dash.page_registry.values()}
        self.assertIn("/fills", paths)

    def test_fill_rows_group_entries_exits_rolls_and_other(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))
                _write_execution_report(loader._paths)

                rows = loader.load_fill_rows()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        roles_by_exec = {row["exec_id"]: row["role"] for row in rows}
        self.assertEqual(roles_by_exec["entry-latest"], "entry_fills")
        self.assertEqual(roles_by_exec["exit-latest"], "exit_fills")
        self.assertEqual(roles_by_exec["roll-closeout"], "roll_fills")
        self.assertEqual(roles_by_exec["roll-entry"], "roll_fills")
        self.assertEqual(roles_by_exec["entry-fallback"], "entry_fills")
        self.assertEqual(roles_by_exec["exit-fallback"], "exit_fills")
        self.assertEqual(roles_by_exec["unknown"], "other_fills")

    def test_render_separates_fill_tables(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))
                _write_execution_report(loader._paths, include_fallback=False)

                create_app()
                fills_page = importlib.import_module("quintet.dashboard.pages.fills")
                children = fills_page.layout()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        text = _component_text(children)
        self.assertIn("Fill Totals", text)
        self.assertIn("Entries", text)
        self.assertIn("Exits", text)
        self.assertIn("Rolls", text)
        self.assertIn("complete", text)
        self.assertNotIn("Order ID", text)
        self.assertNotIn("Exec ID", text)
        self.assertNotIn("entry-latest", text)
        self.assertNotIn("exit-latest", text)
        self.assertNotIn("roll-entry", text)
        self.assertNotIn("101", text)
        self.assertNotIn("201", text)


def _write_execution_report(
    paths: DataPaths,
    *,
    include_fallback: bool = True,
) -> None:
    recent_fills = [
        _fill("entry-latest", 101, "ES", "ESM6", "BOT", "piano", quantity=2),
        _fill("exit-latest", 201, "NQ", "NQM6", "SLD", "piano"),
        _fill("roll-closeout", 302, "ES", "ESM6", "SLD", "piano"),
        _fill("roll-entry", 303, "ES", "ESU6", "BOT", "piano"),
    ]
    if include_fallback:
        recent_fills.extend(
            [
                _fill("entry-fallback", 401, "YM", "YMM6", "BOT", "piano"),
                _fill("exit-fallback", 402, "YM", "YMM6", "SLD", "piano"),
                _fill("unknown", 501, "GC", "GCM6", "BOT", None),
            ]
        )

    report_dir = paths.base / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest_execution_report.json").write_text(
        json.dumps(
            {
                "generated_at": datetime(2026, 4, 30, 16, 30).isoformat(),
                "mode": "live",
                "submitted": [
                    {
                        "status": "submitted",
                        "order_ids": [101, 102],
                        "intent": {
                            "key": [100, "E4"],
                            "symbol": "ES",
                            "quantity": 2,
                        },
                    },
                    {
                        "status": "exit_submitted",
                        "order_id": 201,
                        "intent": {
                            "key": [200, "E4"],
                            "symbol": "NQ",
                            "quantity": 1,
                        },
                    },
                    {
                        "status": "roll_submitted",
                        "closeout_order_ids": [301, 302],
                        "roll_order_ids": [303, 304],
                        "roll_summary": {"quantity": 1},
                        "intent": {
                            "key": [300, "E4"],
                            "symbol": "ES",
                            "quantity": 1,
                        },
                    },
                ],
                "broker_state": {
                    "collected_at": datetime(2026, 4, 30, 16, 29).isoformat(),
                    "account": {"net_liquidation": 100000.0, "currency": "USD"},
                    "positions": [],
                    "open_orders": [],
                    "recent_fills": recent_fills,
                    "recent_errors": [],
                    "next_rth_days": {},
                    "contract_meta": {},
                },
            }
        )
    )


def _fill(
    exec_id: str,
    order_id: int,
    symbol: str,
    local_symbol: str,
    side: str,
    order_ref: str | None,
    quantity: int = 1,
) -> dict:
    return {
        "exec_id": exec_id,
        "order_id": order_id,
        "con_id": order_id + 1000,
        "symbol": symbol,
        "local_symbol": local_symbol,
        "side": side,
        "quantity": quantity,
        "price": 5000.0,
        "time": "20260430 16:10:00",
        "order_ref": order_ref,
    }


def _component_text(component) -> str:
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    if isinstance(component, (list, tuple)):
        return " ".join(_component_text(child) for child in component)
    children = getattr(component, "children", None)
    return _component_text(children)
