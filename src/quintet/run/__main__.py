"""Main entry point for quintet trading system.

Daily pipeline:
    0. Update contracts — fetch contracts still tradeable today from IBKR.
    1. Indicators        — per-system parquets with technical indicators.
    2. Clusters          — cross-sectional k-means on today's VNS strength;
                           centroids and per-product labels held in-process.
    3. Predictions       — `prob` per-row via the system's XGBoost model.
    4. Tau               — pooled Wilson lower-bound walkdown over the
                           per-product 60-bar lookback; one tau per system,
                           in-process only.

Coverage scope: by default the ~95 contracts whose scan window contains
today; with `--force-full-year`, the full ~462-contract year window.
`--no-fetch` skips Step 0; `--no-indicators` skips Steps 1, 2, and 3
(the derived-data bundle).

Usage:
    python -m quintet.run                       # daily run, active today
    python -m quintet.run --no-fetch            # skip IBKR fetch
    python -m quintet.run --no-indicators       # skip derived-data steps
    python -m quintet.run --force-full-year     # rebuild everything, full year
"""

import argparse
import math
import sys
from datetime import date

import pandas as pd

from quintet.config import N_CLUSTERS, PRECISION, SYSTEMS
from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.update_contracts import update_all_contracts
from quintet.data.paths import DataPaths
from quintet.make_predictions import ClusterAssigner, ContractPredictor
from quintet.process_contracts import ContractProcessor
from quintet.tau import compute_system_tau, evaluate_tau_gate


def _build_active_locals(registry: ContractRegistry, today: date) -> set[str]:
    """Local symbols of contracts whose scan window contains today.

    Active means scan has started (start_scan <= today) and trading hasn't
    finished (today <= last_day). Future-listed contracts whose start_scan is
    still in the future are excluded — they have no historical bars yet.
    """
    out: set[str] = set()
    for symbol in registry.get_active_symbols():
        for c in registry.get_contracts_for_product(symbol).values():
            sw = c.scan_window
            if sw.start_scan and sw.start_scan <= today <= sw.last_day:
                out.add(c.local_symbol)
    return out


def step_update_contracts(force: bool) -> None:
    print("=" * 60)
    print(f"STEP 0: Update contracts (IBKR){' [full year]' if force else ''}")
    print("=" * 60)
    update_all_contracts(force=force)


def step_indicators(
    processor: ContractProcessor,
    scope: set[str] | None,
    asof: date | None,
) -> None:
    print("\n" + "=" * 60)
    print("STEP 1: Indicators")
    print("=" * 60)
    for system in SYSTEMS:
        results = processor.process_system(system, active_locals=scope, asof=asof)
        n_files = sum(results.values())
        print(f"  {system}: {n_files} parquet(s) across {len(results)} symbol(s)")


def step_clusters(assigner: ClusterAssigner) -> None:
    print("\n" + "=" * 60)
    print("STEP 2: Clusters")
    print("=" * 60)
    for system in SYSTEMS:
        cluster = assigner.process_system(system)
        if cluster is None:
            print(f"  {system}: cluster OFF (N_CLUSTERS=None)")
            continue

        today = cluster["today"]
        today_str = pd.Timestamp(today).date() if today is not None else "N/A"
        n_in_scan = cluster["n_in_scan"]
        n_products = cluster["n_products"]

        print(
            f"  {system}: Today={today_str}.  "
            f"{n_in_scan} products in scan window, "
            f"{n_products} contributing."
        )

        if cluster["misaligned"]:
            print(f"       Misaligned (last bar < today):")
            for sym, local_sym, last_bar in cluster["misaligned"]:
                last_bar_str = pd.Timestamp(last_bar).date()
                print(f"         {local_sym} ({sym}): {last_bar_str}")

        if cluster["skipped_reason"] is not None:
            n_required = N_CLUSTERS[system]
            print(
                f"       Skipped: {cluster['skipped_reason']} "
                f"(n={n_products}, need ≥{n_required})"
            )
        else:
            cr = ", ".join(f"{v:.4f}" for v in cluster["centroids_r"])
            print(f"       Clustered: centroids_r=[{cr}]")


def step_predictions(
    predictor: ContractPredictor,
    scope: set[str] | None,
) -> None:
    print("\n" + "=" * 60)
    print("STEP 3: Predictions")
    print("=" * 60)
    for system in SYSTEMS:
        results = predictor.process_system(system, active_locals=scope)
        n_scored = sum(results.values())
        print(f"  {system}: {n_scored} parquet(s) scored across {len(results)} symbol(s)")


def step_taus(
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
) -> dict[str, dict]:
    print("\n" + "=" * 60)
    print("STEP 4: Tau (Wilson walkdown, 60-bar lookback)")
    print("=" * 60)
    out: dict[str, dict] = {}
    for system in SYSTEMS:
        result = compute_system_tau(system, today, registry, paths)
        target = PRECISION[system]
        n_pool = result["n_pool"]
        n_pos = result["n_positives"]
        n_products = len(result["products"])
        ls = result.get("lookback_status", {})
        cached = ls.get("cached", 0)
        rebuilt = ls.get("rebuilt", 0)
        base_rate = (n_pos / n_pool) if n_pool else float("nan")

        passes, n_active = evaluate_tau_gate(
            system, today, result["tau"], registry, paths
        )
        out[system] = {"tau_result": result, "gate_passes": passes, "n_active": n_active}

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
                print(f"      pool empty (no eligible products)")
            if not (isinstance(best_lb, float) and math.isnan(best_lb)):
                gap_pp = (best_lb - target) * 100
                print(
                    f"      best wilson-lb seen: {best_lb*100:.2f}% at k={best_lb_k}"
                    f"   (gap {gap_pp:+.2f} pp)"
                )
            print(
                f"      lookback    {n_products} products · "
                f"{cached} cached, {rebuilt} rebuilt"
            )
            print(f"      passed      0 / {n_active} (tau NaN)")
            continue

        tau = result["tau"]
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
        print(
            f"      kept        {best_k} / {n_pool} rows  "
            f"({depth_pct:.0f}%, max k)"
        )
        print(f"      precision   {tp_at_k} / {best_k} = {prec*100:.2f}%")
        print(f"      wilson-lb   {wlb*100:.2f}%   target {target*100:.2f}%")
        print(f"      model lift  {lift_pp:+.2f} pp  (target − base rate)")
        print(
            f"      top-{top_k_n}      {top_k_tp} / {top_k_n} = "
            f"{top_k_prec*100:.1f}%"
        )
        print(f"      base rate   {n_pos} / {n_pool} = {base_rate*100:.2f}%")
        print(
            f"      lookback    {n_products} products · "
            f"{cached} cached, {rebuilt} rebuilt"
        )
        print(f"      passed      {len(passes)} / {n_active}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Quintet trading system - daily pipeline")
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip Step 0 (IBKR contract fetch). Use existing raw CSVs as-is.",
    )
    parser.add_argument(
        "--no-indicators",
        action="store_true",
        help=(
            "Skip Step 1 entirely (indicators, clusters, and predictions are "
            "all bundled). Use only when you want a Step 0 fetch without "
            "rebuilding any derived data."
        ),
    )
    parser.add_argument(
        "--force-full-year",
        action="store_true",
        help=(
            "Run every step over the full year window (~462 contracts) "
            "instead of just contracts active today (~95). Pair with "
            "--no-fetch to rebuild from existing CSVs without re-hitting IBKR."
        ),
    )
    parser.add_argument(
        "--trim-today",
        action="store_true",
        help=(
            "Drop rows whose date == today before computing indicators, "
            "clusters, and predictions. Use mid-session in dev to avoid "
            "IBKR's still-open partial bar."
        ),
    )
    args = parser.parse_args()

    paths = DataPaths()
    registry = ContractRegistry(paths.contracts_json)
    registry.load()

    today = date.today()
    asof: date | None = today if args.trim_today else None
    if args.force_full_year:
        scope: set[str] | None = None
        print("Coverage: all contracts in year window")
    else:
        scope = _build_active_locals(registry, today)
        print(f"Coverage: {len(scope)} active contracts today")
    if asof is not None:
        print(f"Trim: dropping rows >= {asof}")

    if args.no_fetch:
        print("=" * 60)
        print("STEP 0: Update contracts (skipped via --no-fetch)")
        print("=" * 60)
    else:
        step_update_contracts(force=args.force_full_year)

    processor = ContractProcessor()
    predictor = ContractPredictor(master=processor.master)
    assigner = ClusterAssigner(master=processor.master, registry=registry)

    if args.no_indicators:
        print("\n" + "=" * 60)
        print("STEPS 1-4: skipped via --no-indicators")
        print("=" * 60)
    else:
        step_indicators(processor, scope, asof)
        step_clusters(assigner)
        step_predictions(predictor, scope)
        step_taus(today, registry, paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
