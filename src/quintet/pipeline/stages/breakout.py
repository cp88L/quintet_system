"""Step 6: Breakout gate.

For each product in the funnel, `breakout_pass = (high < res_n)`. With
`--trim-today` the latest bar is yesterday's complete bar, so this
checks "did yesterday's high already cross yesterday's resistance" —
if so, the breakout is in the rear-view and we skip the trade.
Products missing `high` or `res_n` are filtered out (None).
"""

from __future__ import annotations

from quintet.config import SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages.base import PipelineStage


class BreakoutStage(PipelineStage):
    name = "STEP 6: Breakout (high < Res_N)"

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)
        for system in SYSTEMS:
            funnel = ctx.funnels.get(system)
            if funnel is None:
                continue
            for p in funnel.products.values():
                if p.high is None or p.res_n is None:
                    p.breakout_pass = False
                else:
                    p.breakout_pass = p.high < p.res_n

            n_universe = len(funnel.products)
            n_breakout = funnel.count_passing("breakout")
            n_surviving = funnel.count_surviving_through("tau", "cluster", "breakout")
            print(
                f"  {system}: breakout {n_breakout} / {n_universe}  →  "
                f"surviving {n_surviving} (tau ∩ cluster ∩ breakout)"
            )
