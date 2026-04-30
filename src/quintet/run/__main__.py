"""Main entry point for the quintet daily pipeline.

The pipeline is a fixed sequence of stages from
`quintet.pipeline.stages.PIPELINE`:

    0. Fetch         — IBKR contract bars
    1. Indicators    — per-system technical indicators
    2. Predictions   — XGBoost prob per row
    3. BuildFunnel   — populate per-system ProductCandidate state
    4. Tau           — Wilson walkdown + per-product tau gate
    5. Clusters      — k-means cluster_id + INCLUDE_CLUSTERS gate
    6. Breakout      — high < Res_N gate
    7. Snapshot      — write data/processed/_funnel.json
    8. Trade         — optional broker-neutral dry-run or live execution

Each stage is a `PipelineStage` subclass that owns its own print block
and reads/writes `PipelineContext`. CLI flags map to per-stage
`skip(args)` predicates.

Coverage scope: by default the contracts whose scan window contains
today; with `--force-full-year`, the full-year contract set.
`--no-fetch` skips Step 0; `--no-indicators` skips Steps 1-2 (indicators
and predictions, which are the disk-writing stages). The funnel still
builds from existing parquets, so Steps 3-7 still run.

Usage:
    python -m quintet.run                       # daily run, active today
    python -m quintet.run --no-fetch            # skip IBKR fetch
    python -m quintet.run --no-indicators       # skip data-rebuild stages
    python -m quintet.run --force-full-year     # rebuild full-year window
    python -m quintet.run --trim-today          # drop today's partial bar
    python -m quintet.run --dry-run             # write broker-neutral trade reports
    python -m quintet.run --live                # submit supported trade intents
"""

import argparse
import sys
from datetime import date

from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.flows.daily import run_trade_dry_run, run_trade_live
from quintet.pipeline.context import PipelineContext
from quintet.pipeline.stages import PIPELINE


def _build_active_locals(registry: ContractRegistry, today: date) -> set[str]:
    """Local symbols of contracts whose scan window contains today.

    Active means scan has started (`start_scan <= today`) and trading
    hasn't finished (`today <= last_day`). Future-listed contracts whose
    `start_scan` is still in the future are excluded — they have no
    historical bars yet.
    """
    out: set[str] = set()
    for symbol in registry.get_active_symbols():
        for c in registry.get_contracts_for_product(symbol).values():
            sw = c.scan_window
            if sw.start_scan and sw.start_scan <= today <= sw.last_day:
                out.add(c.local_symbol)
    return out


def _parse_args() -> argparse.Namespace:
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
            "Skip Steps 1-2 (indicators + predictions — the disk-writing "
            "stages). Funnel-build, tau, cluster, breakout, and snapshot "
            "still run against existing parquets."
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
            "Drop rows whose date == today before computing indicators "
            "and predictions. Use mid-session in dev to avoid IBKR's "
            "still-open partial bar."
        ),
    )
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "After the signal pipeline, build a broker-neutral trade plan "
            "from current IBKR account, positions, and open orders. No order "
            "placement."
        ),
    )
    execution.add_argument(
        "--live",
        action="store_true",
        help=(
            "After the signal pipeline, submit supported trade intents to "
            "the configured IBKR paper Gateway."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    ctx = PipelineContext.build(args)

    if args.force_full_year:
        ctx.scope = None
        print("Coverage: all contracts in year window")
    else:
        ctx.scope = _build_active_locals(ctx.registry, ctx.today)
        print(f"Coverage: {len(ctx.scope)} active contracts today")
    if ctx.asof is not None:
        print(f"Trim: dropping rows >= {ctx.asof}")

    for stage in PIPELINE:
        if stage.skip(args):
            msg = stage.skip_message()
            if msg:
                print("\n" + "=" * 60)
                print(msg)
                print("=" * 60)
            continue
        stage.run(ctx)

    if args.dry_run or args.live:
        print("\n" + "=" * 60)
        print("STEP 8: Trade live" if args.live else "STEP 8: Trade dry-run")
        print("=" * 60)
        if args.live:
            broker_state, plan, report = run_trade_live(ctx)
        else:
            from quintet.broker.ibkr.state import IbkrBrokerGateway

            broker_state = IbkrBrokerGateway().collect_state()
            plan, report = run_trade_dry_run(ctx, broker_state=broker_state)
        print(
            f"  broker state: equity={broker_state.account.net_liquidation:.2f} "
            f"positions={len(broker_state.positions)} "
            f"open_orders={len(broker_state.open_orders)}"
        )
        n_place = sum(
            1 for i in plan.intents if i.__class__.__name__ == "PlaceBracketIntent"
        )
        report_dir = ctx.paths.base / "reports"
        print(f"  signals: {len(plan.signals)}")
        print(f"  intents: {len(plan.intents)}")
        print(f"  place brackets: {n_place}")
        print(f"  skipped: {len(plan.skipped)}")
        print(f"  report mode: {report.mode}")
        print(f"  submitted: {report.counts.submitted}")
        print(f"  cancel requested: {report.counts.cancel_requested}")
        print(f"  modified: {report.counts.modified}")
        print(f"  reported only: {report.counts.reported_only}")
        print(f"  alerts: {report.counts.alerts}")
        print(f"  threw: {report.counts.threw}")
        if report.counts.dry_run:
            print(f"  dry run actions: {report.counts.dry_run}")
        print(f"  wrote {report_dir / 'latest_trade_plan.json'}")
        print(f"  wrote {report_dir / 'latest_execution_report.json'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
