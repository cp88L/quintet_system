"""Step 4: Tau (Wilson walkdown) and per-product tau gate.

Computes today's tau per system via the existing `compute_system_tau`
helper, persists `_tau.json`, then walks the funnel and sets
`tau_pass = (prob is not None and prob >= tau)` on each `ProductCandidate`.
NaN-tau systems set `tau_pass = False` for everyone.
"""

from __future__ import annotations

import math

from quintet.config import PRECISION, SYSTEMS
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages.base import PipelineStage
from quintet.tau import compute_system_tau


class TauStage(PipelineStage):
    name = "STEP 4: Tau (Wilson walkdown, 60-bar lookback)"

    def run(self, ctx: PipelineContext) -> None:
        print("\n" + "=" * 60)
        print(self.name)
        print("=" * 60)
        for system in SYSTEMS:
            self._run_system(system, ctx)

    def _run_system(self, system: str, ctx: PipelineContext) -> None:
        result = compute_system_tau(
            system,
            ctx.today,
            ctx.registry,
            ctx.paths,
            force=getattr(ctx.args, "force_tau", False),
        )
        ctx.tau_results[system] = result
        target = PRECISION[system]
        n_pool = result["n_pool"]
        n_pos = result["n_positives"]
        n_products = len(result["products"])
        ls = result.get("lookback_status", {})
        cached = ls.get("cached", 0)
        rebuilt = ls.get("rebuilt", 0)
        base_rate = (n_pos / n_pool) if n_pool else float("nan")

        funnel = ctx.funnels.get(system)
        tau = result["tau"]
        tau_is_nan = tau is None or (isinstance(tau, float) and math.isnan(tau))
        if funnel is not None:
            funnel.tau = None if tau_is_nan else float(tau)
            for p in funnel.products.values():
                if tau_is_nan or p.prob is None:
                    p.tau_pass = False
                else:
                    p.tau_pass = bool(p.prob >= tau)

        n_universe = len(funnel.products) if funnel else 0
        n_passed = funnel.count_passing("tau") if funnel else 0

        if not result["gate_pass"]:
            best_lb = result.get("best_lb_seen", float("nan"))
            best_lb_k = result.get("best_lb_k", 0)
            print(f"\n  {system} ✗ NO SIGNAL")
            if n_pool:
                print(
                    f"      base rate   {n_pos} / {n_pool} = "
                    f"{base_rate*100:.2f}% < target {target*100:.2f}%"
                )
            else:
                print("      pool empty (no eligible products)")
            if not (isinstance(best_lb, float) and math.isnan(best_lb)):
                gap_pp = (best_lb - target) * 100
                print(
                    f"      best wilson-lb seen: {best_lb*100:.2f}% at k={best_lb_k}"
                    f"   (gap {gap_pp:+.2f} pp)"
                )
            print(f"      lookback    {n_products} products · {cached} cached, {rebuilt} rebuilt")
            print(f"      passed      0 / {n_universe} (tau NaN)")
            return

        best_k = result["best_k"]
        tp_at_k = result["tp_at_k"]
        prec = result["precision_at_k"]
        wlb = result["wilson_lb_at_k"]
        lift_pp = (target - base_rate) * 100
        top_k_n = result["top_k_n"]
        top_k_tp = result["top_k_tp"]
        top_k_prec = result["top_k_precision"]
        depth_pct = best_k / n_pool * 100

        print(f"\n  {system} ✓ PASS   →  fire on prob ≥ {tau:.4f}")
        print(f"      kept        {best_k} / {n_pool} rows  ({depth_pct:.0f}%, max k)")
        print(f"      precision   {tp_at_k} / {best_k} = {prec*100:.2f}%")
        print(f"      wilson-lb   {wlb*100:.2f}%   target {target*100:.2f}%")
        print(f"      model lift  {lift_pp:+.2f} pp  (target − base rate)")
        print(f"      top-{top_k_n}      {top_k_tp} / {top_k_n} = {top_k_prec*100:.1f}%")
        print(f"      base rate   {n_pos} / {n_pool} = {base_rate*100:.2f}%")
        print(f"      lookback    {n_products} products · {cached} cached, {rebuilt} rebuilt")
        print(f"      passed      {n_passed} / {n_universe}")
