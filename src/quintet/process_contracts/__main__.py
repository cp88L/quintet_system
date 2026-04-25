"""CLI for processing contracts into a subsystem's processed/ tree."""

import argparse

from quintet.config import SYSTEMS
from quintet.process_contracts import ContractProcessor


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add indicators to raw contract data for a given subsystem."
    )
    parser.add_argument(
        "--system", "-S",
        required=True,
        choices=SYSTEMS,
        help="Subsystem alias (e.g., C4)",
    )
    parser.add_argument(
        "--symbol", "-s",
        help="Process a single product symbol (e.g., GC). "
             "If omitted, processes the entire system universe.",
    )
    args = parser.parse_args()

    processor = ContractProcessor()

    if args.symbol:
        count = processor.process_symbol(args.system, args.symbol)
        print(f"{args.system}/{args.symbol}: processed {count} file(s)")
        return 0

    # Validate symbol scope: warn if --symbol isn't in this system's universe
    universe = processor.master.get_products_for_system(args.system)
    print(f"Processing {args.system} ({len(universe)} active product(s))")
    results = processor.process_system(args.system)
    total = sum(results.values())
    print(f"\n{args.system}: processed {total} file(s) across {len(results)} symbol(s)")
    for symbol, count in sorted(results.items()):
        print(f"  {symbol}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
