"""CLI for adding `prob` predictions to a subsystem's processed parquets."""

import argparse

from quintet.config import SYSTEMS
from quintet.make_predictions import ContractPredictor


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score processed contracts with the system's XGBoost model."
    )
    parser.add_argument(
        "--system", "-S",
        required=True,
        choices=SYSTEMS,
        help="Subsystem alias (e.g., C4)",
    )
    parser.add_argument(
        "--symbol", "-s",
        help="Score a single product symbol (e.g., GC). "
             "If omitted, scores the entire system universe.",
    )
    args = parser.parse_args()

    predictor = ContractPredictor()

    if args.symbol:
        count = predictor.process_symbol(args.system, args.symbol)
        print(f"{args.system}/{args.symbol}: scored {count} file(s)")
        return 0

    universe = predictor.master.get_products_for_system(args.system)
    print(f"Scoring {args.system} ({len(universe)} active product(s))")
    results = predictor.process_system(args.system)
    total = sum(results.values())
    print(f"\n{args.system}: scored {total} file(s) across {len(results)} symbol(s)")
    for symbol, count in sorted(results.items()):
        print(f"  {symbol}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
