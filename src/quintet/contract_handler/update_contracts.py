"""Update contracts - keep a rotating year of contracts on disk.

For each active product, the on-disk set is the contract about to expire
(smallest last_day >= today) plus every prior contract back through one
full cycle of the product's active months — i.e., until the same
month-letter recurs. For example, if the next-to-expire contract is 26M,
the set is 26M, 26J, 26G, 25Z, 25V, 25Q, 25M (the previous 25M closes
the cycle).

Each run prunes raw CSVs whose contract has fallen out of the cycle.
Already-cached contracts whose last_day has passed are skipped on download
(immutable). The next-to-expire contract and in-flight contracts are
always re-fetched so today's bars land on disk.
"""

import logging
from datetime import date, datetime
from pathlib import Path

from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.historical_bars import (
    BarsRequest,
    HistoricalBars,
    make_contract_by_id,
)
from quintet.contract_handler.product_master import ProductMaster
from quintet.contract_handler.schema import ContractInfo
from quintet.data.paths import DataPaths


def setup_logging(log_path: Path) -> logging.Logger:
    """Set up logging to file and console."""
    logger = logging.getLogger("update_contracts")
    logger.setLevel(logging.INFO)
    # Avoid duplicate handlers if called multiple times in one process
    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def _year_window(
    registry: ContractRegistry,
    symbol: str,
    today: date,
) -> list[ContractInfo]:
    """Rotating-year set per product.

    Includes:
      - Backward cycle: contracts whose contract_month is in
        [boundary_ym, current_ym], where current is the next-to-expire
        contract (smallest last_day >= today) and boundary_ym is the same
        month one year earlier.
      - Forward-active: any contract whose scan window contains today
        (start_scan <= today <= last_day). This catches forward-listed
        contracts that are already tradeable but expire after `current`.
    """
    contracts = registry.get_contracts_for_product(symbol)
    if not contracts:
        return []

    candidates = [c for c in contracts.values() if c.scan_window.last_day >= today]
    if not candidates:
        return []
    current = min(candidates, key=lambda c: c.scan_window.last_day)

    cur_year = int(current.contract_month[:4])
    cur_month = current.contract_month[4:]
    boundary_ym = f"{cur_year - 1}{cur_month}"

    in_window = [
        c for c in contracts.values()
        if (boundary_ym <= c.contract_month <= current.contract_month)
        or (
            c.scan_window.start_scan
            and c.scan_window.start_scan <= today <= c.scan_window.last_day
        )
    ]
    in_window.sort(key=lambda c: c.contract_month)
    return in_window


def update_all_contracts(
    reference_date: date | None = None,
    force: bool = False,
) -> None:
    """Maintain a rotating year of contracts per active product.

    Default mode fetches only contracts still tradeable today (last_day >=
    today). `force=True` fetches the full year window — useful for cold
    cache, indicator math changes, or model swaps.
    """
    today = reference_date or date.today()
    paths = DataPaths()
    paths.raw.mkdir(parents=True, exist_ok=True)
    log = setup_logging(paths.raw / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    log.info(f"Starting update for {today}")

    registry = ContractRegistry(paths.contracts_json)
    registry.load()
    master = ProductMaster(paths.product_master_csv)
    master.load()

    fetch_list: list[tuple[BarsRequest, Path]] = []  # (request, output csv path)
    pruned = 0

    for symbol, config in master.get_active_products().items():
        if not registry.is_product_active(symbol):
            continue

        window = _year_window(registry, symbol, today)
        if not window:
            log.warning(f"{symbol}: no contract pending today")
            continue

        # Prune raw CSVs whose contract has fallen out of the cycle.
        window_locals = {c.local_symbol for c in window}
        raw_dir = paths.raw / symbol
        if raw_dir.exists():
            for f in raw_dir.glob("*.csv"):
                if f.stem not in window_locals:
                    log.info(f"  Pruning {symbol}/{f.name} (out of cycle)")
                    f.unlink()
                    pruned += 1

        for contract in window:
            local_symbol = contract.local_symbol
            file_path = paths.raw_dir(symbol) / f"{local_symbol}.csv"

            # CSI-only placeholders have no IBKR id and can't be fetched live.
            if contract.con_id == 0:
                continue

            # Default: only fetch contracts still tradeable today.
            if not force and contract.scan_window.last_day < today:
                continue

            # Skip if cached and the contract has finished trading (immutable).
            if file_path.exists() and today > contract.scan_window.last_day:
                continue

            ibkr_contract = make_contract_by_id(contract.con_id, contract.exchange)
            ibkr_contract.localSymbol = local_symbol
            fetch_list.append((
                BarsRequest(
                    local_symbol=local_symbol,
                    contract=ibkr_contract,
                    hourly=config.hourly,
                ),
                file_path,
            ))

    if pruned:
        log.info(f"Pruned {pruned} out-of-cycle CSV(s)")

    if not fetch_list:
        log.info("Nothing to fetch — all contracts cached.")
        return

    BATCH_SIZE = 40
    total = len(fetch_list)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    log.info(f"Fetching {total} contract(s) in {n_batches} batch(es) of up to {BATCH_SIZE}...")

    bars = HistoricalBars()
    saved = 0
    no_data_locals: list[str] = []
    i = 0
    try:
        for b in range(n_batches):
            chunk = fetch_list[b * BATCH_SIZE:(b + 1) * BATCH_SIZE]
            log.info(f"Batch {b + 1}/{n_batches} ({len(chunk)} contracts)...")

            requests = [req for req, _ in chunk]
            results = bars.get_bars_for_many(requests)

            for req, file_path in chunk:
                i += 1
                data = results.get(req.local_symbol, [])
                if not data:
                    log.warning(f"  [{i}/{total}] {req.local_symbol}: no data")
                    no_data_locals.append(req.local_symbol)
                    continue
                with open(file_path, "w") as f:
                    f.write("timestamp,open,high,low,close,volume\n")
                    for bar in data:
                        f.write(
                            f"{bar.timestamp.isoformat()},{bar.open},{bar.high},"
                            f"{bar.low},{bar.close},{bar.volume}\n"
                        )
                log.info(f"  [{i}/{total}] {req.local_symbol}: {len(data)} bars")
                saved += 1
    finally:
        bars.close()

    log.info(f"Done — saved {saved}, no-data {len(no_data_locals)}")
    if no_data_locals:
        log.info(f"  No-data contracts: {', '.join(no_data_locals)}")


if __name__ == "__main__":
    update_all_contracts()
