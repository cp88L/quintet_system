"""Main entry point for quintet trading system.

Daily pipeline:
    0. Update contracts — fetch contracts still tradeable today from IBKR.
    1. Process contracts — per-system parquets with indicators.
    2. Make predictions — append `prob` column per parquet.

By default, only contracts whose scan window contains today are touched
(typically ~95 contracts). Use --force-full-year to fetch, process, and
score every contract in the rotating-year window (~462) — for first-time
setup, indicator math changes, or model swaps.

Usage:
    python -m quintet.run                     # Daily (active contracts only)
    python -m quintet.run --no-update         # Skip Step 0
    python -m quintet.run --force-full-year   # All three steps over the full year
"""

import argparse
import sys
from datetime import date

from quintet.config import SYSTEMS
from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.update_contracts import update_all_contracts
from quintet.data.paths import DataPaths
from quintet.make_predictions import ContractPredictor
from quintet.process_contracts import ContractProcessor


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


def step_process_contracts(
    processor: ContractProcessor,
    active_locals: set[str] | None,
) -> None:
    print("\n" + "=" * 60)
    print("STEP 1: Process contracts (indicators)")
    print("=" * 60)
    for system in SYSTEMS:
        results = processor.process_system(system, active_locals=active_locals)
        total = sum(results.values())
        print(f"  {system}: {total} parquet(s) across {len(results)} symbol(s)")


def step_make_predictions(
    predictor: ContractPredictor,
    active_locals: set[str] | None,
) -> None:
    print("\n" + "=" * 60)
    print("STEP 2: Make predictions (prob)")
    print("=" * 60)
    for system in SYSTEMS:
        results = predictor.process_system(system, active_locals=active_locals)
        total = sum(results.values())
        print(f"  {system}: {total} parquet(s) scored")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quintet trading system - daily pipeline")
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip Step 0 contract update",
    )
    parser.add_argument(
        "--force-full-year",
        action="store_true",
        help=(
            "Run all three steps over the full year window (~462 contracts) "
            "instead of just contracts active today (~95). Forces Step 0 to "
            "fetch every contract in the year cycle, Step 1 to (re)compute "
            "indicators on every raw CSV, and Step 2 to (re)score every "
            "parquet. Use for first-time setup, indicator math changes, or "
            "model swaps."
        ),
    )
    args = parser.parse_args()

    paths = DataPaths()
    registry = ContractRegistry(paths.contracts_json)
    registry.load()

    today = date.today()
    if args.force_full_year:
        active_locals: set[str] | None = None
    else:
        active_locals = _build_active_locals(registry, today)
        print(f"Active contracts today: {len(active_locals)}")

    if args.no_update:
        print("=" * 60)
        print("STEP 0: Update contracts (skipped via --no-update)")
        print("=" * 60)
    else:
        step_update_contracts(force=args.force_full_year)

    processor = ContractProcessor()
    predictor = ContractPredictor(master=processor.master)

    step_process_contracts(processor, active_locals)
    step_make_predictions(predictor, active_locals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
