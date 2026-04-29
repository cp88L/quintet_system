"""Step 5: Cross-sectional cluster compute and gate.

Runs `ClusterAssigner.process_system(system)` to produce today's
per-product `cluster_id`, then writes those onto the funnel and applies
the `INCLUDE_CLUSTERS[system]` filter as `cluster_pass`. Systems with
`N_CLUSTERS[system] = None` disable the filter (`cluster_pass = True`
for every product).
"""

from __future__ import annotations

import pandas as pd

from quintet.config import INCLUDE_CLUSTERS, N_CLUSTERS, SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages.base import PipelineStage


class ClusterStage(PipelineStage):
    name = "STEP 5: Clusters"

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)
        for system in SYSTEMS:
            self._run_system(system, ctx)

    def _run_system(self, system: str, ctx: PipelineContext) -> None:
        funnel = ctx.funnels.get(system)
        n_universe = len(funnel.products) if funnel else 0
        n_tau_pass = funnel.count_passing("tau") if funnel else 0

        cluster = ctx.assigner.process_system(system)
        include = INCLUDE_CLUSTERS.get(system)

        # Filter disabled (E13): everyone passes the cluster gate.
        if N_CLUSTERS.get(system) is None or cluster is None:
            if funnel is not None:
                for p in funnel.products.values():
                    p.cluster_pass = True
            print(
                f"  {system}: cluster filter OFF.  "
                f"tau {n_tau_pass} / {n_universe}  →  cluster {n_tau_pass} / {n_tau_pass}"
            )
            return

        labels = cluster.get("labels_by_product") or {}
        if funnel is not None:
            for sym, p in funnel.products.items():
                cid = labels.get(sym)
                p.cluster_id = int(cid) if cid is not None else None
                if include is None:
                    p.cluster_pass = True
                else:
                    p.cluster_pass = p.cluster_id is not None and p.cluster_id in include

        n_passed = funnel.count_passing("cluster") if funnel else 0
        # Survivors: products that cleared BOTH tau and cluster.
        n_survivors = (
            sum(1 for p in funnel.products.values() if p.tau_pass and p.cluster_pass)
            if funnel
            else 0
        )

        today = cluster.get("today")
        today_str = pd.Timestamp(today).date() if today is not None else "N/A"
        skipped = cluster.get("skipped_reason")
        if skipped:
            n_required = N_CLUSTERS[system]
            print(
                f"  {system}: skipped ({skipped}; n={cluster['n_products']}, need ≥{n_required})  "
                f"→  {n_survivors} / {n_tau_pass} survive"
            )
            return

        cr = ", ".join(f"{v:.4f}" for v in cluster["centroids_r"])
        include_str = "{" + ", ".join(str(c) for c in sorted(include)) + "}" if include else "—"
        print(
            f"  {system}: today={today_str}  centroids_r=[{cr}]  include={include_str}"
        )
        print(
            f"      tau {n_tau_pass} / {n_universe}  →  cluster {n_passed} of all  "
            f"→  {n_survivors} / {n_tau_pass} survive both"
        )
