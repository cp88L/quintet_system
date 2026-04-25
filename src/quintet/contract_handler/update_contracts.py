"""Update contracts - download historical data for all active contracts."""

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


def update_all_contracts(reference_date: date | None = None) -> None:
    """Download 1Y of bars for the contract currently in scan window per active product.

    Only the symbol whose scan window contains today is fetched; expired and
    not-yet-active months are ignored. The historical archive lives at
    DataPaths.raw (currently STORAGE_ROOT/historical/).
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

    requests: list[BarsRequest] = []
    targets: dict[str, Path] = {}  # local_symbol -> output csv path

    for symbol, config in master.get_active_products().items():
        if not registry.is_product_active(symbol):
            continue

        local_symbol = registry.get_active_contract(symbol, as_of=today)
        if local_symbol is None:
            log.warning(f"{symbol}: no contract in scan window today")
            continue

        contract = next(
            c for c in registry.get_contracts_for_product(symbol).values()
            if c.local_symbol == local_symbol
        )

        # CSI-only placeholders have no IBKR id and can't be fetched live.
        if contract.con_id == 0:
            continue

        ibkr_contract = make_contract_by_id(contract.con_id, contract.exchange)
        ibkr_contract.localSymbol = local_symbol
        requests.append(BarsRequest(
            local_symbol=local_symbol,
            contract=ibkr_contract,
            hourly=config.hourly,
        ))
        targets[local_symbol] = paths.raw_dir(symbol) / f"{local_symbol}.csv"

    log.info(f"Fetching {len(requests)} contracts concurrently...")
    bars = HistoricalBars()
    try:
        results = bars.get_bars_for_many(requests)
    finally:
        bars.close()

    saved = 0
    for local_symbol, file_path in targets.items():
        data = results.get(local_symbol, [])
        if not data:
            log.error(f"  ERROR: No data for {local_symbol}")
            continue
        with open(file_path, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            for bar in data:
                f.write(f"{bar.timestamp.isoformat()},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}\n")
        log.info(f"  Saved {file_path}")
        saved += 1
    log.info(f"Done — saved {saved}/{len(targets)}")


if __name__ == "__main__":
    update_all_contracts()
