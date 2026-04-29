"""Step 2: XGBoost predictions per system, written to processed parquets."""

from __future__ import annotations

import argparse

from quintet.config import SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages.base import PipelineStage


class PredictionsStage(PipelineStage):
    name = "STEP 2: Predictions"

    def skip(self, args: argparse.Namespace) -> bool:
        return getattr(args, "no_indicators", False)

    def skip_message(self) -> str:
        return ""  # IndicatorsStage already prints the bundled-skip message

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)
        for system in SYSTEMS:
            results = ctx.predictor.process_system(system, active_locals=ctx.scope)
            n_scored = sum(results.values())
            print(f"  {system}: {n_scored} parquet(s) scored across {len(results)} symbol(s)")
