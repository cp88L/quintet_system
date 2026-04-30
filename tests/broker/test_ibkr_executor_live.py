from datetime import date
from unittest import TestCase

import pandas as pd

from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.product_master import ProductMaster
from quintet.broker.ibkr.state import IbkrStateClient
from quintet.data.paths import DataPaths
from quintet.execution.ibkr import IbkrExecutor
from quintet.execution.models import PlaceBracketIntent
from quintet.trading.models import Side, TradePlan
from quintet.trading.prices import round_to_tick


class LiveIbkrExecutorTests(TestCase):
    def test_places_and_cancels_single_bracket_order(self) -> None:
        intent = _build_far_away_es_intent()
        client = IbkrStateClient()
        order_ids: list[int] = []

        client.connect_and_run()
        try:
            account = client.get_account_state()
            positions = client.get_positions()
            self.assertGreater(account.net_liquidation, 0.0)
            self.assertIsInstance(positions, list)

            report = IbkrExecutor().execute_connected(
                TradePlan(intents=[intent]),
                client,
            )
            self.assertEqual(report.mode, "live")
            self.assertEqual(len(report.submitted), 1)
            order_ids = list(report.submitted[0]["order_ids"])
            self.assertEqual(len(order_ids), 2)
            self.assertEqual(len(report.events), 2)
        finally:
            for order_id in reversed(order_ids):
                client.cancel_order(order_id)
            if order_ids:
                client.get_open_orders()
            client.disconnect_and_stop()


def _build_far_away_es_intent() -> PlaceBracketIntent:
    paths = DataPaths()
    registry = ContractRegistry(paths.contracts_json)
    registry.load()
    master = ProductMaster(paths.product_master_csv)
    master.load()

    symbol = "ES"
    system = "E4"
    product = master.get_product(symbol)
    local_symbol = registry.get_active_contract(symbol, as_of=date.today())
    contract = next(
        c
        for c in registry.get_contracts_for_product(symbol).values()
        if c.local_symbol == local_symbol
    )

    parquet_path = paths.processed_dir(system, symbol) / f"{local_symbol}.parquet"
    close = float(pd.read_parquet(parquet_path, columns=["close"]).iloc[-1]["close"])
    entry_price = round_to_tick(close + 200.0, product.min_tick)
    stop_price = round_to_tick(close - 200.0, product.min_tick)
    risk_per_contract = (entry_price - stop_price) * product.multiplier

    return PlaceBracketIntent(
        key=(contract.con_id, system),
        side=Side.LONG,
        symbol=symbol,
        local_symbol=local_symbol,
        exchange=contract.exchange or product.exchange,
        currency=product.currency,
        quantity=1,
        entry_action=Side.LONG.entry_action,
        entry_order_type="STP LMT",
        entry_stop_price=entry_price,
        entry_limit_price=entry_price,
        protective_action=Side.LONG.protective_action,
        protective_order_type="STP LMT",
        protective_stop_price=stop_price,
        protective_limit_price=stop_price,
        risk_per_contract=risk_per_contract,
        total_risk=risk_per_contract,
    )
