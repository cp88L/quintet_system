"""Step 7: Funnel snapshot.

Writes the full per-system per-product funnel state to one JSON at
`data/processed/_funnel.json` plus the funnel reduction summary at the
top of the payload. Overwrites every run; the file is the canonical
end-of-run state for dashboard consumption.
"""

from __future__ import annotations

import json

from quintet.config import SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages.base import PipelineStage


class SnapshotStage(PipelineStage):
    name = "STEP 7: Snapshot"

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)

        snapshot = {
            "today": str(ctx.today),
            "systems": {sys: ctx.funnels[sys].to_dict() for sys in SYSTEMS if sys in ctx.funnels},
        }

        out_path = ctx.paths.processed / "_funnel.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(snapshot, f, indent=2, default=str)

        print(f"  wrote {out_path}")
        print()
        print("  Funnel reduction:")
        print(f"  {'sys':<5} {'universe':>9} {'tau':>6} {'cluster':>8} {'breakout':>9} {'actionable':>11}")
        for system in SYSTEMS:
            f = ctx.funnels.get(system)
            if f is None:
                continue
            print(
                f"  {system:<5} {len(f.products):>9} "
                f"{f.count_passing('tau'):>6} "
                f"{f.count_passing('cluster'):>8} "
                f"{f.count_passing('breakout'):>9} "
                f"{len(f.actionable_products):>11}"
            )
