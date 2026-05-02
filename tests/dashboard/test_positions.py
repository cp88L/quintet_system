import json
import importlib
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase

import dash
from dash import dcc
import pandas as pd

from quintet.dashboard.app import create_app
from quintet.dashboard.data import loader
from quintet.data.paths import DataPaths


class PositionsDashboardTests(TestCase):
    def test_positions_page_is_registered(self) -> None:
        create_app()

        paths = {page["path"] for page in dash.page_registry.values()}
        self.assertIn("/positions", paths)

    def test_position_rows_reconcile_held_missing_and_unknown_positions(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                paths = DataPaths(Path(tmpdir))
                _seed_reference(paths)
                _write_execution_report(paths)
                loader._paths = paths
                loader.clear_cache()

                rows = loader.load_position_rows()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        self.assertEqual([row["status"] for row in rows], ["held", "missing_stop", "unknown_system"])
        held = rows[0]
        self.assertEqual(held["system"], "E4")
        self.assertEqual(held["side"], "long")
        self.assertEqual(held["local_symbol"], "ESM6")
        self.assertEqual(held["entry_price"], 5200.0)
        self.assertEqual(str(held["entry_date"]), "2026-04-29")
        self.assertEqual(held["stop_price"], 5100.0)
        self.assertEqual(held["stop_order_id"], 77)
        self.assertEqual(str(held["estimated_last_day"]), "2026-06-18")
        self.assertEqual(str(held["official_last_day"]), "2026-06-18")

        self.assertEqual(rows[1]["local_symbol"], "PAM6")
        self.assertIsNone(rows[1]["stop_price"])
        self.assertEqual(rows[2]["local_symbol"], "NQM6")
        self.assertIsNone(rows[2]["system"])

    def test_position_rows_compute_return_and_current_risk_from_on_disk_prices(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                paths = DataPaths(Path(tmpdir))
                _seed_reference(paths)
                _seed_processed_contract(paths)
                _write_execution_report(paths)
                loader._paths = paths
                loader.clear_cache()

                rows = loader.load_position_rows()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        held = rows[0]
        self.assertEqual(held["current_price"], 5220.0)
        self.assertEqual(held["unrealized_pnl"], 1000.0)
        self.assertAlmostEqual(held["return_pct"], (5220.0 - 5200.0) / 5200.0)
        self.assertEqual(held["current_risk"], 6000.0)

        self.assertIsNone(rows[1]["current_risk"])

    def test_position_chart_uses_on_disk_contract_data_and_draws_entry_stop(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                paths = DataPaths(Path(tmpdir))
                _seed_reference(paths)
                _seed_processed_contract(paths)
                _write_execution_report(paths)
                loader._paths = paths
                loader.clear_cache()

                create_app()
                positions_page = importlib.import_module("quintet.dashboard.pages.positions")
                held = loader.load_position_rows()[0]
                block = positions_page._position_chart_block(held)
                fig = block.children[2].figure.to_dict()
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        shape_prices = {
            shape.get("y0")
            for shape in fig["layout"].get("shapes", [])
            if shape.get("y0") == shape.get("y1")
        }
        self.assertIn(5200.0, shape_prices)
        self.assertIn(5100.0, shape_prices)
        shape_dates = {
            str(shape.get("x0"))[:10]
            for shape in fig["layout"].get("shapes", [])
            if shape.get("x0") == shape.get("x1")
        }
        self.assertIn("2026-04-29", shape_dates)
        trace_types = [trace["type"] for trace in fig["data"]]
        self.assertIn("ohlc", trace_types)

    def test_render_charts_every_position_status_with_on_disk_data(self) -> None:
        old_paths = loader._paths
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                paths = DataPaths(Path(tmpdir))
                _seed_reference(paths)
                _seed_processed_contract(paths)
                _seed_processed_contract(paths, "C4", "PA", "PAM6")
                _seed_processed_contract(paths, "E4", "NQ", "NQM6")
                _write_execution_report(paths)
                loader._paths = paths
                loader.clear_cache()

                create_app()
                positions_page = importlib.import_module("quintet.dashboard.pages.positions")
                children = positions_page.render(None, None)
        finally:
            loader._paths = old_paths
            loader.clear_cache()

        chart_graphs = [
            graph
            for graph in _find_graphs(children)
            if graph.figure.to_dict()["layout"].get("height") != 200
        ]
        self.assertEqual(len(chart_graphs), 3)


def _seed_reference(paths: DataPaths) -> None:
    paths.reference.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "symbol": "ES",
                "active": 1,
                "multiplier": 50.0,
                "priceMagnifier": 1,
                "longName": "E-mini S&P 500",
                "c4": 0,
                "cs4": 0,
                "e4": 1,
                "e7": 1,
                "e13": 1,
            },
            {
                "symbol": "PA",
                "active": 1,
                "multiplier": 100.0,
                "priceMagnifier": 1,
                "longName": "Palladium",
                "c4": 1,
                "cs4": 1,
                "e4": 0,
                "e7": 0,
                "e13": 0,
            },
            {
                "symbol": "NQ",
                "active": 1,
                "multiplier": 20.0,
                "priceMagnifier": 1,
                "longName": "E-mini Nasdaq 100",
                "c4": 0,
                "cs4": 0,
                "e4": 1,
                "e7": 1,
                "e13": 1,
            },
        ]
    ).to_csv(paths.product_master_csv, index=False)

    paths.contracts_json.write_text(
        json.dumps(
            {
                "products": {
                    "ES": {
                        "longName": "E-mini S&P 500",
                        "contracts": {
                            "202606": {
                                "localSymbol": "ESM6",
                                "start_scan": "2026-04-01",
                                "end_scan": "2026-06-15",
                                "last_day": "2026-06-18",
                            }
                        },
                    },
                    "PA": {
                        "longName": "Palladium",
                        "contracts": {
                            "202606": {
                                "localSymbol": "PAM6",
                                "start_scan": "2026-04-01",
                                "end_scan": "2026-05-20",
                                "last_day": "2026-05-26",
                            }
                        },
                    },
                    "NQ": {
                        "longName": "E-mini Nasdaq 100",
                        "contracts": {
                            "202606": {
                                "localSymbol": "NQM6",
                                "start_scan": "2026-04-01",
                                "end_scan": "2026-06-15",
                                "last_day": "2026-06-18",
                            }
                        },
                    },
                }
            }
        )
    )


def _seed_processed_contract(
    paths: DataPaths,
    system: str = "E4",
    symbol: str = "ES",
    contract: str = "ESM6",
) -> None:
    out_dir = paths.processed / system / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-04-28", "2026-04-29", "2026-04-30"]),
            "open": [5190.0, 5200.0, 5210.0],
            "high": [5210.0, 5220.0, 5230.0],
            "low": [5175.0, 5185.0, 5195.0],
            "close": [5200.0, 5210.0, 5220.0],
            "volume": [1000, 1200, 1100],
            "Sup_4": [5100.0, 5100.0, 5100.0],
            "Res_4": [5250.0, 5250.0, 5250.0],
            "prob": [0.2, 0.3, 0.4],
        }
    ).to_parquet(out_dir / f"{contract}.parquet", index=False)


def _find_graphs(component) -> list[dcc.Graph]:
    if isinstance(component, dcc.Graph):
        return [component]
    if isinstance(component, (list, tuple)):
        out: list[dcc.Graph] = []
        for child in component:
            out.extend(_find_graphs(child))
        return out

    children = getattr(component, "children", None)
    if children is None:
        return []
    return _find_graphs(children)


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
                        {
                            "account": "DU123",
                            "con_id": 200,
                            "symbol": "PA",
                            "local_symbol": "PAM6",
                            "quantity": 2,
                            "avg_cost": 162250.0,
                        },
                        {
                            "account": "DU123",
                            "con_id": 300,
                            "symbol": "NQ",
                            "local_symbol": "NQM6",
                            "quantity": 1,
                            "avg_cost": 400000.0,
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
                            "limit_price": 5100.0,
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
                            "status": "Submitted",
                            "system": "E7",
                            "aux_price": 18900.0,
                        },
                    ],
                    "recent_fills": [
                        {
                            "exec_id": "0001",
                            "order_id": 10,
                            "con_id": 100,
                            "symbol": "ES",
                            "local_symbol": "ESM6",
                            "side": "BOT",
                            "quantity": 1,
                            "price": 5200.0,
                            "time": "20260429 15:20:00",
                            "order_ref": "piano",
                        },
                        {
                            "exec_id": "0002",
                            "order_id": 11,
                            "con_id": 200,
                            "symbol": "PA",
                            "local_symbol": "PAM6",
                            "side": "BOT",
                            "quantity": 2,
                            "price": 1622.5,
                            "time": "20260428 15:20:00",
                            "order_ref": "trumpet",
                        },
                    ],
                    "next_rth_days": {
                        "100": "2026-06-18",
                        "200": "2026-05-25",
                        "300": "2026-06-18",
                    },
                    "contract_meta": {
                        "100": {
                            "con_id": 100,
                            "symbol": "ES",
                            "local_symbol": "ESM6",
                            "exchange": "CME",
                            "currency": "USD",
                            "multiplier": 50.0,
                            "min_tick": 0.25,
                            "price_magnifier": 1,
                            "last_trade_date": "2026-04-30",
                            "last_day": "2026-04-30",
                        },
                        "200": {
                            "con_id": 200,
                            "symbol": "PA",
                            "local_symbol": "PAM6",
                            "exchange": "NYMEX",
                            "currency": "USD",
                            "multiplier": 100.0,
                            "min_tick": 0.5,
                            "price_magnifier": 1,
                            "last_trade_date": "2026-06-26",
                            "last_day": "2026-06-26",
                        },
                    },
                },
            }
        )
    )
