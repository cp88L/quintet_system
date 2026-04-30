"""Build the per-system funnel from the processed parquets.

Runs after Predictions. For each system, for each product in the
master universe, finds today's active contract via the registry,
reads the contract's processed parquet, and pulls the latest row's
`prob`, `Sup_N`, `Res_N`, `high` into a `ProductCandidate`. Products
with no active contract today, no parquet, or no usable last row are
skipped — only candidates with a valid latest row enter the funnel.
"""

from __future__ import annotations

import argparse

import pandas as pd

from quintet.config import INDICATORS, SYSTEM_LABEL, SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.funnel import ProductCandidate, SystemFunnel
from quintet.pipeline.stages.base import PipelineStage


class BuildFunnelStage(PipelineStage):
    name = "STEP 3: Build funnel"

    def skip(self, args: argparse.Namespace) -> bool:
        # Building the funnel is cheap and required by every downstream stage.
        return False

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)
        for system in SYSTEMS:
            funnel = self._build(system, ctx)
            ctx.funnels[system] = funnel
            print(f"  {system}: {len(funnel.products)} candidates")

    def _build(self, system: str, ctx: PipelineContext) -> SystemFunnel:
        funnel = SystemFunnel(system=system, today=ctx.today)
        label = SYSTEM_LABEL[system]
        sup_col, res_col = f"Sup_{label}", f"Res_{label}"
        rspos_col = next((c for c in INDICATORS[system] if c.startswith("RSpos_")), None)
        cols = ["timestamp", "high", "prob", sup_col, res_col]
        if rspos_col:
            cols.append(rspos_col)

        for symbol in ctx.master.get_products_for_system(system):
            local_symbol = ctx.registry.get_active_contract(symbol, as_of=ctx.today)
            if local_symbol is None:
                continue

            parquet_path = ctx.paths.processed_dir(system, symbol) / f"{local_symbol}.parquet"
            if not parquet_path.exists():
                continue

            df = pd.read_parquet(parquet_path, columns=[c for c in cols if c])
            if df.empty:
                continue

            row = df.iloc[-1]
            contracts = ctx.registry.get_contracts_for_product(symbol)
            contract = next(
                (c for c in contracts.values() if c.local_symbol == local_symbol),
                None,
            )
            if contract is None:
                continue

            funnel.products[symbol] = ProductCandidate(
                product=symbol,
                local_symbol=local_symbol,
                con_id=contract.con_id,
                prob=_to_optional_float(row.get("prob")),
                res_n=_to_optional_float(row.get(res_col)),
                sup_n=_to_optional_float(row.get(sup_col)),
                rspos_n=_to_optional_float(row.get(rspos_col)) if rspos_col else None,
                high=_to_optional_float(row.get("high")),
            )
        return funnel


def _to_optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f
