"""Per-system tau gate evaluation. In-memory only; not persisted.

Walks the contract registry for products with an active contract today,
reads each contract's processed parquet, and returns the products whose
last-row `prob` clears today's tau. Called from `step_taus` after
`compute_system_tau` returns.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.product_master import ProductMaster
from quintet.data.paths import DataPaths


def evaluate_tau_gate(
    system: str,
    today: date,
    tau: float,
    registry: ContractRegistry,
    paths: DataPaths,
) -> tuple[list[dict], int]:
    """Return `(passes, n_active)` for `system` at `today`.

    `passes` is a list of `{product, local_symbol, con_id, prob}` dicts
    for products whose latest processed-parquet `prob` clears `tau`.
    `n_active` counts every product with an active contract today,
    regardless of whether it had data or passed — it is the denominator
    used in the print summary.

    NaN tau short-circuits the parquet reads but still walks the
    registry so the denominator stays honest.
    """
    passes: list[dict] = []
    n_active = 0
    tau_is_nan = tau is None or (isinstance(tau, float) and math.isnan(tau))

    master = ProductMaster(paths.product_master_csv)
    master.load()
    symbols = sorted(master.get_products_for_system(system).keys())

    for symbol in symbols:
        local_symbol = registry.get_active_contract(symbol, as_of=today)
        if local_symbol is None:
            continue
        n_active += 1
        if tau_is_nan:
            continue

        parquet_path = paths.processed_dir(system, symbol) / f"{local_symbol}.parquet"
        if not parquet_path.exists():
            continue

        df = pd.read_parquet(parquet_path, columns=["prob"])
        if df.empty:
            continue

        prob = df["prob"].iloc[-1]
        if pd.isna(prob):
            continue

        if prob >= tau:
            contracts = registry.get_contracts_for_product(symbol)
            contract = next(
                (c for c in contracts.values() if c.local_symbol == local_symbol),
                None,
            )
            passes.append({
                "product": symbol,
                "local_symbol": local_symbol,
                "con_id": contract.con_id if contract else None,
                "prob": float(prob),
            })

    return passes, n_active
