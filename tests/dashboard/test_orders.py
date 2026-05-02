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


class OrdersDashboardTests(TestCase):
    def test_orders_page_is_registered(self) -> None:
        create_app()

        paths = {page["path"] for page in dash.page_registry.values()}
        self.assertIn("/orders", paths)

    def test_order_rows_read_latest_broker_snapshot(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))
                _write_execution_report(loader._paths)

                rows = loader.load_order_rows()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        self.assertEqual([row["order_id"] for row in rows], [77, 88, 89])
        first = rows[0]
        self.assertEqual(first["system"], "E4")
        self.assertEqual(first["symbol"], "ES")
        self.assertEqual(first["local_symbol"], "ESM6")
        self.assertEqual(first["action"], "SELL")
        self.assertEqual(first["order_type"], "STP LMT")
        self.assertEqual(first["quantity"], 1)
        self.assertEqual(first["status"], "Submitted")
        self.assertEqual(first["role"], "current_position_stops")
        self.assertEqual(first["aux_price"], 5100.0)
        self.assertEqual(first["limit_price"], 5099.0)
        self.assertEqual(first["order_ref"], "quintet:E4")
        self.assertEqual(first["tif"], "GTC")
        self.assertTrue(first["transmit"])

    def test_render_filters_orders_by_system_status_and_symbol(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))
                _write_execution_report(loader._paths)

                create_app()
                orders_page = importlib.import_module("quintet.dashboard.pages.orders")
                children = orders_page.render("E4", "Submitted", "NQ")
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        text = _component_text(children)
        self.assertIn("88", text)
        self.assertIn("NQM6", text)
        self.assertNotIn("77", text)
        self.assertNotIn("89", text)

    def test_render_separates_current_and_old_position_stops(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                loader._paths = DataPaths(Path(tmpdir))
                _write_execution_report(loader._paths)

                create_app()
                orders_page = importlib.import_module("quintet.dashboard.pages.orders")
                children = orders_page.render(None, None, None)
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        cards = _cards_by_header(children)
        self.assertIn("Current Position Stops", cards)
        self.assertIn("Old Position Stops", cards)

        current_text = _component_text(cards["Current Position Stops"])
        old_text = _component_text(cards["Old Position Stops"])
        self.assertIn("77", current_text)
        self.assertNotIn("88", current_text)
        self.assertIn("88", old_text)
        self.assertNotIn("77", old_text)


def _write_execution_report(paths: DataPaths) -> None:
    report_dir = paths.base / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest_execution_report.json").write_text(
        json.dumps(
            {
                "generated_at": datetime(2026, 4, 30, 16, 30).isoformat(),
                "mode": "dry_run",
                "broker_state": {
                    "collected_at": datetime(2026, 4, 30, 16, 29).isoformat(),
                    "account": {"net_liquidation": 100000.0, "currency": "USD"},
                    "positions": [
                        {
                            "account": "DU123",
                            "con_id": 100,
                            "symbol": "ES",
                            "local_symbol": "ESM6",
                            "quantity": 1,
                            "avg_cost": 260000.0,
                        },
                    ],
                    "open_orders": [
                        {
                            "order_id": 77,
                            "perm_id": 10077,
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
                            "order_ref": "quintet:E4",
                            "tif": "GTC",
                            "transmit": True,
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
                        {
                            "order_id": 89,
                            "con_id": 300,
                            "symbol": "NQ",
                            "local_symbol": "NQM6",
                            "action": "SELL",
                            "order_type": "STP LMT",
                            "quantity": 1,
                            "status": "PreSubmitted",
                            "system": "E7",
                            "aux_price": 18900.0,
                        },
                    ],
                },
            }
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


def _cards_by_header(component) -> dict[str, object]:
    cards = {}
    children_to_scan = component if isinstance(component, list) else [component]
    for child in children_to_scan:
        children = getattr(child, "children", None)
        if not isinstance(children, list) or not children:
            continue
        header = children[0]
        text = _component_text(header)
        if text:
            cards[text] = child
    return cards
