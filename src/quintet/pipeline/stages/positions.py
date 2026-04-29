"""Step 7: Position dedupe.

For each ProductCandidate, set `position_pass = not tracker.is_held(con_id, system)`.
The tracker is currently a stub — it loads from `paths.positions_json`
when that file exists, otherwise reports zero held positions and every
candidate passes. When IBKR position capture is wired, replace the
tracker's `load()` with the real fetch; the stage shape doesn't change.
"""

from __future__ import annotations

from quintet.config import SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.positions import PositionTracker
from quintet.pipeline.stages.base import PipelineStage


class PositionStage(PipelineStage):
    name = "STEP 7: Positions (dedupe by con_id × system)"

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)

        tracker = PositionTracker(ctx.paths.positions_json)
        tracker.load()

        if tracker.is_stub:
            print("  (stub: no positions file at "
                  f"{ctx.paths.positions_json.name} — IBKR capture not wired)")
        else:
            print(f"  loaded {len(tracker)} held (con_id × system) key(s)")

        for system in SYSTEMS:
            funnel = ctx.funnels.get(system)
            if funnel is None:
                continue
            for p in funnel.products.values():
                p.position_pass = not tracker.is_held(p.con_id, system)
            n_passed = funnel.count_passing("position")
            n_actionable = len(funnel.actionable_products)
            print(
                f"  {system}: position {n_passed} / {len(funnel.products)}  "
                f"→  actionable {n_actionable}"
            )
