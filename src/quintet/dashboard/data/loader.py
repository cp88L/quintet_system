"""Data loading utilities for the dashboard."""

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from quintet.config import INDICATORS, PRECISION, SYSTEM_LABEL, SYSTEMS
from quintet.data.paths import DataPaths
from quintet.tau.threshold import calculate_threshold


@dataclass
class ContractDates:
    start_scan: datetime | None
    end_scan: datetime | None
    last_day: datetime | None


_paths = DataPaths()
_contracts_data: dict | None = None
_product_master: pd.DataFrame | None = None


def _load_contracts_json() -> dict:
    global _contracts_data
    if _contracts_data is None:
        json_path = _paths.contracts_json
        if json_path.exists():
            with open(json_path) as f:
                _contracts_data = json.load(f)
        else:
            _contracts_data = {}
    return _contracts_data


def _load_product_master() -> pd.DataFrame:
    global _product_master
    if _product_master is None:
        pm_path = _paths.product_master_csv
        if pm_path.exists():
            _product_master = pd.read_csv(pm_path)
        else:
            _product_master = pd.DataFrame()
    return _product_master


def get_systems_for(symbol: str) -> list[str]:
    """Return system aliases whose flag is set for this symbol in the master CSV.

    Order matches `quintet.config.SYSTEMS` (C4, CS4, E4, E7, E13).
    """
    pm = _load_product_master()
    if pm.empty:
        return []
    row = pm[pm["symbol"] == symbol]
    if row.empty:
        return []
    r = row.iloc[0]
    return [sys for sys in SYSTEMS if int(r.get(sys.lower(), 0)) == 1]


def get_symbols() -> list[str]:
    """Return active symbols from the product master, sorted alphabetically."""
    pm = _load_product_master()
    if pm.empty:
        return []
    active = pm[pm["active"] == 1]
    return sorted(active["symbol"].tolist())


def get_contracts(symbol: str) -> list[str]:
    """List contracts available for a symbol across all its systems, newest first."""
    systems = get_systems_for(symbol)
    if not systems:
        return []

    available_files: set[str] = set()
    for sys in systems:
        sys_dir = _paths.processed / sys / symbol
        if sys_dir.exists():
            available_files.update(f.stem for f in sys_dir.glob("*.parquet"))

    if not available_files:
        return []

    data = _load_contracts_json()
    contracts_json = data.get("products", {}).get(symbol, {}).get("contracts", {})

    contracts_with_month = [
        (cm, info["localSymbol"])
        for cm, info in contracts_json.items()
        if info.get("localSymbol") in available_files
    ]
    contracts_with_month.sort(key=lambda x: x[0], reverse=True)
    return [c[1] for c in contracts_with_month]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Settle",
        "volume": "Volume",
    })


@lru_cache(maxsize=64)
def load_contract(symbol: str, contract: str) -> pd.DataFrame:
    """Merge per-system processed parquets for one contract.

    Each system file contributes its OHLCV (deduped), its `Sup_w/Res_w`
    pair (window per `STRUCTURE_WINDOWS[system]`, deduped on conflict),
    and its `prob` column renamed to `prob_{system}`. Returned frame is
    indexed by timestamp and column-normalized for the chart code
    (open→Open, high→High, low→Low, close→Settle, volume→Volume).
    """
    systems = get_systems_for(symbol)
    if not systems:
        raise FileNotFoundError(f"No systems configured for {symbol}")

    merged: pd.DataFrame | None = None
    seen_sr: set[str] = set()

    for sys in systems:
        path = _paths.processed / sys / symbol / f"{contract}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)

        sup_col, res_col = INDICATORS[sys][0], INDICATORS[sys][1]
        keep = ["timestamp", "open", "high", "low", "close", "volume"]
        if sup_col not in seen_sr:
            keep.extend([sup_col, res_col])
            seen_sr.add(sup_col)
        keep.append("prob")

        slim = df[[c for c in keep if c in df.columns]].copy()
        slim = slim.rename(columns={"prob": f"prob_{sys}"})

        if merged is None:
            merged = slim
        else:
            new_cols = [c for c in slim.columns if c not in merged.columns or c == "timestamp"]
            merged = merged.merge(slim[new_cols], on="timestamp", how="outer")

    if merged is None or merged.empty:
        raise FileNotFoundError(f"No parquet files found for {symbol}/{contract}")

    merged = merged.sort_values("timestamp").set_index("timestamp")
    return _normalize_columns(merged)


def clear_cache() -> None:
    load_contract.cache_clear()


def _parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def get_contract_dates(symbol: str, contract: str) -> ContractDates:
    data = _load_contracts_json()
    products = data.get("products", {})
    if symbol not in products:
        return ContractDates(None, None, None)

    for info in products[symbol].get("contracts", {}).values():
        if info.get("localSymbol") == contract:
            return ContractDates(
                start_scan=_parse_date(info.get("start_scan", "")),
                end_scan=_parse_date(info.get("end_scan", "")),
                last_day=_parse_date(info.get("last_day", "")),
            )
    return ContractDates(None, None, None)


_funnel_data: dict | None = None


def _load_funnel() -> dict:
    """Load and cache `processed/_funnel.json` (per-run snapshot of all systems)."""
    global _funnel_data
    if _funnel_data is None:
        path = _paths.funnel_json
        if path.exists():
            with open(path) as f:
                _funnel_data = json.load(f)
        else:
            _funnel_data = {}
    return _funnel_data


def get_in_scan_for_system(system: str) -> list[dict]:
    """Per-system in-scan contracts with gate state, ordered best-first.

    Reads `processed/_funnel.json`. For each product in the system's universe
    returns a dict: `symbol, contract, prob, cluster_id, tau_pass,
    cluster_pass, breakout_pass, actionable`. Sort: actionable first, then
    by number of gates passed, then by prob descending.
    """
    funnel = _load_funnel()
    sys_data = funnel.get("systems", {}).get(system)
    if not sys_data:
        return []

    out: list[dict] = []
    for p in sys_data.get("products", []):
        out.append(
            {
                "symbol": p.get("product"),
                "contract": p.get("local_symbol"),
                "prob": p.get("prob"),
                "cluster_id": p.get("cluster_id"),
                "tau_pass": bool(p.get("tau_pass", False)),
                "cluster_pass": bool(p.get("cluster_pass", False)),
                "breakout_pass": bool(p.get("breakout_pass", False)),
                "actionable": bool(p.get("actionable", False)),
            }
        )

    def _key(r: dict) -> tuple:
        breakout_only = (
            r["breakout_pass"] and not r["tau_pass"] and not r["cluster_pass"]
        )
        prob = r["prob"] if r["prob"] is not None else float("-inf")
        # Order: actionable first, then cluster_pass (cluster supersedes prob),
        # then by prob desc, with breakout-only items pushed to the very bottom.
        return (not r["actionable"], not r["cluster_pass"], breakout_only, -prob)

    out.sort(key=_key)
    return out


def get_funnel_summary(system: str) -> dict:
    """Return the per-system funnel header (counts + tau)."""
    return _load_funnel().get("systems", {}).get(system, {})


def get_product_info(symbol: str) -> dict:
    data = _load_contracts_json()
    product_data = data.get("products", {}).get(symbol, {})
    return {k: v for k, v in product_data.items() if k != "contracts"}


def get_month_name(local_symbol: str) -> str:
    from quintet.dashboard.config import MONTH_CODES

    if len(local_symbol) < 2:
        return ""
    month_code = local_symbol[-2].upper()
    return MONTH_CODES.get(month_code, "")


def format_chart_title(symbol: str, contract: str) -> str:
    info = get_product_info(symbol)
    long_name = info.get("longName", symbol)
    month_name = get_month_name(contract)
    if month_name:
        return f"{long_name} - {contract} ({month_name})"
    return f"{long_name} - {contract}"


# =============================================================================
# Tau / lookback loaders
# =============================================================================

def load_tau_snapshot(system: str) -> dict:
    """Read processed/{system}/_tau.json. Returns {} when the file is missing."""
    path = _paths.tau_json_path(system)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def list_lookback_products(system: str) -> list[str]:
    """Sorted product list backed by parquet files under {system}/_lookback/."""
    lookback_dir = _paths.lookback_dir(system)
    if not lookback_dir.exists():
        return []
    return sorted(p.stem for p in lookback_dir.glob("*.parquet"))


@lru_cache(maxsize=256)
def load_lookback(system: str, product: str) -> pd.DataFrame:
    """Load the per-system rolling 60-bar lookback for one product.

    Schema on disk: timestamp, contract, open, high, low, close, prob,
    Label_{N}. Returned frame is timestamp-indexed and column-normalized
    (open→Open, etc.) so chart code can reuse the OHLC convention.
    """
    path = _paths.lookback_dir(system) / f"{product}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No lookback parquet for {system}/{product}")

    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    return _normalize_columns(df)


def load_latest_trade_plan() -> dict:
    """Read the latest broker-neutral trade plan report."""
    return _load_json(_paths.base / "reports" / "latest_trade_plan.json")


def load_latest_execution_report() -> dict:
    """Read the latest execution report."""
    return _load_json(_paths.base / "reports" / "latest_execution_report.json")


def _load_json(path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def compute_product_precision(system: str, product: str) -> dict | None:
    """Per-product Wilson walkdown — the same logic that produces the
    system-level snapshot, applied to one product's 60-bar pool.

    Returns a dict with `tau, n, best_k, precision_at_k, wilson_lb_at_k,
    n_tp, pos_rate, hit`. `hit` is True when the per-product walkdown
    finds a valid k. Returns None if the product has no lookback or
    the required Label column is missing.
    """
    label = SYSTEM_LABEL[system]
    label_col = f"Label_{label}"
    try:
        df = load_lookback(system, product)
    except FileNotFoundError:
        return None
    if label_col not in df.columns or "prob" not in df.columns:
        return None

    probs = df["prob"].to_numpy(dtype=float)
    labels = df[label_col].to_numpy(dtype=float)
    mask = ~(np.isnan(probs) | np.isnan(labels))
    probs = probs[mask]
    labels = labels[mask]

    if len(probs) == 0:
        return None

    target = PRECISION[system]
    tau, diag = calculate_threshold(probs, labels, target)

    best_k = int(diag["best_k"])
    n_tp = int(round(diag["precision_at_k"] * best_k)) if best_k else 0
    pos_rate = float(labels.mean()) if len(labels) else 0.0
    hit = not (isinstance(tau, float) and np.isnan(tau))

    return {
        "product": product,
        "tau": float(tau) if hit else None,
        "n": int(diag["n"]),
        "best_k": best_k,
        "n_tp": n_tp,
        "precision_at_k": float(diag["precision_at_k"]) if hit else None,
        "wilson_lb_at_k": float(diag["wilson_lb_at_k"]) if hit else None,
        "pos_rate": pos_rate,
        "hit": hit,
    }
