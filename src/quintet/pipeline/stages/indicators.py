"""Step 1: Per-system technical indicators."""

from __future__ import annotations

import argparse

from quintet.config import SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages.base import PipelineStage


class IndicatorsStage(PipelineStage):
    name = "STEP 1: Indicators"

    def skip(self, args: argparse.Namespace) -> bool:
        return getattr(args, "no_indicators", False)

    def skip_message(self) -> str:
        return "STEPS 1-3: skipped via --no-indicators"

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)
        for system in SYSTEMS:
            results = ctx.processor.process_system(
                system, active_locals=ctx.scope, asof=ctx.asof
            )
            n_files = sum(results.values())
            print(f"  {system}: {n_files} parquet(s) across {len(results)} symbol(s)")
