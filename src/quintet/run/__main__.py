"""Main entry point for quintet trading system.

Daily pipeline (currently stub — only Step 0 wired up):
    0. Update contracts (download latest data from IBKR)

Usage:
    python -m quintet.run
"""

import sys

from quintet.contract_handler.update_contracts import update_all_contracts


def step_update_contracts() -> int:
    """Step 0: Update contracts - download latest data from IBKR."""
    print("=" * 60)
    print("STEP 0: Updating contracts (downloading from IBKR)")
    print("=" * 60)

    update_all_contracts()
    return 0


def main() -> int:
    """Run quintet trading system - daily pipeline."""
    step_update_contracts()
    return 0


if __name__ == "__main__":
    sys.exit(main())
