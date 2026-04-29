"""Step 0: Fetch contract bars from IBKR."""

from __future__ import annotations

import argparse

from quintet.contract_handler.update_contracts import update_all_contracts
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages.base import PipelineStage


class FetchStage(PipelineStage):
    name = "STEP 0: Fetch (IBKR)"

    def skip(self, args: argparse.Namespace) -> bool:
        return getattr(args, "no_fetch", False)

    def skip_message(self) -> str:
        return "STEP 0: Fetch (skipped via --no-fetch)"

    def run(self, ctx: PipelineContext) -> None:
        force = getattr(ctx.args, "force_full_year", False)
        suffix = " [full year]" if force else ""
        print("=" * 60)
        print(f"{self.name}{suffix}")
        print("=" * 60)
        update_all_contracts(force=force)
