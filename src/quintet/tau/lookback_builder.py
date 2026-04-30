"""Per-system rotating lookback DataFrame for tau calibration.

For a given system S and date `today`, build the per-product 60-bar pool
of (prob, Label) pairs from contracts whose `last_day < today` (strictly
expired).

Walk-back per product is newest-expired-first. Each contract's processed
parquet is loaded, labels are computed in-memory via
`tau.label_calculator.add_labels`, the result is restricted to the scan
area and to non-NaN (prob, Label) rows, and contracts are stacked until
the per-product accumulator reaches LOOKBACK_WINDOW (60). On the
contract that overshoots, only the most-recent `bars_needed` rows are
taken (`tail`), so the per-product DataFrame is exactly LOOKBACK_WINDOW
rows when enough history exists, fewer in early-warmup.

Persistence: `refresh_product_lookback` writes the rolling 60 bars to
`processed/{system}/_lookback/{product}.parquet`. The on-disk file is
treated as up-to-date if its last `contract` value matches the current
newest-expired contract for that product — so we only rebuild when a new
contract crosses its `last_day`. `refresh_system_lookback` and
`refresh_all_lookbacks` extend this across products and systems.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from quintet.config import (
    LOOKBACK_WINDOW,
    SYSTEM_LABEL,
    SYSTEM_SIDE,
    SYSTEMS,
)
from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.schema import ContractInfo
from quintet.data.paths import DataPaths
from quintet.tau.label_calculator import add_labels


def _eligible_contracts(
    contracts: dict[str, ContractInfo], today: date
) -> list[ContractInfo]:
    """Contracts strictly past last_day, sorted most-recently-expired first."""
    expired = [c for c in contracts.values() if c.scan_window.last_day < today]
    expired.sort(key=lambda c: c.scan_window.last_day, reverse=True)
    return expired


def _load_and_finalize(
    parquet_path: Path,
    label: int,
    side: str,
    contract: ContractInfo,
) -> pd.DataFrame:
    """Load processed parquet, add labels, restrict to scan area, drop NaNs.

    Returns rows in chronological order with at minimum:
    timestamp, prob, Label_{label}, contract.
    """
    df = pd.read_parquet(parquet_path)
    df = add_labels(df, label, side, contract.scan_window.last_day)

    label_col = f'Label_{label}'

    timestamps = pd.to_datetime(df['timestamp'])
    dates = timestamps.dt.date

    sw = contract.scan_window
    start = sw.start_scan if sw.start_scan is not None else dates.min()
    in_scan = (dates >= start) & (dates <= sw.end_scan)

    df = df.loc[in_scan].copy()
    df = df.dropna(subset=['prob', label_col])

    df = df.sort_values('timestamp').reset_index(drop=True)
    df['contract'] = contract.local_symbol
    return df


def build_product_lookback(
    system: str,
    product: str,
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
    target_bars: int = LOOKBACK_WINDOW,
) -> pd.DataFrame:
    """Build the per-product rotating lookback DataFrame for one system.

    Walks back through `product`'s contracts under `system`,
    most-recently-expired first, accumulating non-NaN scan-area
    (prob, Label) rows until `target_bars` is reached. Returns at
    most `target_bars` rows in chronological order.

    A contract present in the registry but missing from
    processed/{system}/{product}/ is logged and skipped.
    """
    label = SYSTEM_LABEL[system]
    side = SYSTEM_SIDE[system]

    contracts = _eligible_contracts(
        registry.get_contracts_for_product(product), today
    )
    if not contracts:
        return pd.DataFrame()

    product_dir = paths.processed / system / product
    collected: list[pd.DataFrame] = []
    total_bars = 0

    for contract in contracts:
        if total_bars >= target_bars:
            break

        parquet_path = product_dir / f"{contract.local_symbol}.parquet"
        if not parquet_path.exists():
            print(
                f"  [lookback] {system}/{product}/{contract.local_symbol}: "
                f"processed parquet missing — skipping"
            )
            continue

        scan_df = _load_and_finalize(parquet_path, label, side, contract)
        if len(scan_df) == 0:
            continue

        bars_needed = target_bars - total_bars
        if len(scan_df) <= bars_needed:
            collected.append(scan_df)
            total_bars += len(scan_df)
        else:
            collected.append(scan_df.tail(bars_needed))
            total_bars += bars_needed

    if not collected:
        return pd.DataFrame()

    collected.reverse()
    return pd.concat(collected, ignore_index=True)


def build_system_lookback(
    system: str,
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
    target_bars: int = LOOKBACK_WINDOW,
) -> dict[str, pd.DataFrame]:
    """Build per-product rotating lookback DataFrames for every product in `system`.

    Iterates products that exist on disk under processed/{system}/ and
    returns a `{product: DataFrame}` map. Products with no eligible
    expired contracts are omitted from the map.
    """
    system_dir = paths.processed / system
    if not system_dir.exists():
        return {}

    out: dict[str, pd.DataFrame] = {}
    for product_dir in sorted(p for p in system_dir.iterdir() if p.is_dir()):
        product = product_dir.name
        df = build_product_lookback(
            system, product, today, registry, paths, target_bars
        )
        if not df.empty:
            out[product] = df
    return out


def build_all_lookbacks(
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
    target_bars: int = LOOKBACK_WINDOW,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Build the {system: {product: DataFrame}} map for every system (in-memory)."""
    return {
        system: build_system_lookback(system, today, registry, paths, target_bars)
        for system in SYSTEMS
    }


# =============================================================================
# Persistence layer (mirrors quartet's `data/lookback/{PRODUCT}.parquet` shape)
# =============================================================================

def _output_columns(system: str) -> list[str]:
    """Schema for the on-disk per-product lookback parquet."""
    label = SYSTEM_LABEL[system]
    return [
        "timestamp", "contract",
        "open", "high", "low", "close",
        "prob", f"Label_{label}",
    ]


def needs_rebuild(lookback_path: Path, newest_expired_local: str) -> tuple[bool, str]:
    """Decide whether the on-disk lookback for a product needs rebuilding.

    Compares the last `contract` value in the existing parquet to the
    current newest-expired contract for the product. Match → no rebuild;
    mismatch (or missing/unreadable file) → rebuild.
    """
    if not lookback_path.exists():
        return True, "no existing file"
    try:
        df = pd.read_parquet(lookback_path)
    except Exception as e:  # corrupt/unreadable file
        return True, f"unreadable ({e})"
    if df.empty or "contract" not in df.columns:
        return True, "empty or missing 'contract' column"
    last = df["contract"].iloc[-1]
    if last != newest_expired_local:
        return True, f"new contract: {newest_expired_local} (was {last})"
    return False, f"up to date ({newest_expired_local})"


def refresh_product_lookback(
    system: str,
    product: str,
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
    target_bars: int = LOOKBACK_WINDOW,
    force: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Build-or-load the per-product lookback and persist it on rebuild.

    Returns `(df, status)` where `status` is one of:
      - "cached"     — on-disk file matches newest expired, loaded as-is
      - "rebuilt"    — rebuilt and rewritten because expired set advanced or force=True
      - "no_eligible" — product has no expired contracts yet
    """
    contracts = _eligible_contracts(
        registry.get_contracts_for_product(product), today
    )
    if not contracts:
        return pd.DataFrame(), "no_eligible"
    newest_local = contracts[0].local_symbol

    lookback_path = paths.lookback_dir(system) / f"{product}.parquet"
    rebuild, _reason = needs_rebuild(lookback_path, newest_local)

    if not force and not rebuild:
        return pd.read_parquet(lookback_path), "cached"

    df = build_product_lookback(system, product, today, registry, paths, target_bars)
    if df.empty:
        return df, "no_eligible"

    cols = _output_columns(system)
    out = df[[c for c in cols if c in df.columns]].copy()
    out.to_parquet(lookback_path, index=False)
    return out, "rebuilt"


def refresh_system_lookback(
    system: str,
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
    target_bars: int = LOOKBACK_WINDOW,
    force: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """Refresh per-product lookbacks for all products in `system`.

    Returns `({product: df}, {status_count: int})` where the second dict
    summarizes how many products were cached vs rebuilt this run.
    """
    system_dir = paths.processed / system
    if not system_dir.exists():
        return {}, {}

    out: dict[str, pd.DataFrame] = {}
    counts: dict[str, int] = {"cached": 0, "rebuilt": 0, "no_eligible": 0}
    for product_dir in sorted(
        p for p in system_dir.iterdir() if p.is_dir() and not p.name.startswith("_")
    ):
        product = product_dir.name
        df, status = refresh_product_lookback(
            system, product, today, registry, paths, target_bars, force=force
        )
        counts[status] = counts.get(status, 0) + 1
        if not df.empty:
            out[product] = df
    return out, counts


def refresh_all_lookbacks(
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
    target_bars: int = LOOKBACK_WINDOW,
    force: bool = False,
) -> dict[str, tuple[dict[str, pd.DataFrame], dict[str, int]]]:
    """Refresh `_lookback/*.parquet` across every system. {system: (lookbacks, counts)}."""
    return {
        system: refresh_system_lookback(
            system, today, registry, paths, target_bars, force=force
        )
        for system in SYSTEMS
    }
