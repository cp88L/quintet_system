"""Data loading utilities for the dashboard."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from quintet.broker.models import (
    AccountState,
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    BrokerState,
    ContractMeta,
)
from quintet.config import (
    INDICATORS,
    PRECISION,
    SYSTEM_LABEL,
    SYSTEM_SIDE,
    SYSTEMS,
    VOICE_TO_SYSTEM,
)
from quintet.data.paths import DataPaths
from quintet.tau.threshold import calculate_threshold
from quintet.trading.models import Side
from quintet.trading.reconcile import ENTRY_TYPES, STOP_TYPES, reconcile_state
from quintet.trading.risk import calculate_position_risk


@dataclass
class ContractDates:
    start_scan: datetime | None
    end_scan: datetime | None
    last_day: datetime | None
    official_last_day: datetime | None = None


_paths = DataPaths()


def _file_mtime(path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


@lru_cache(maxsize=4)
def _load_contracts_json_cached(mtime: float) -> dict:
    path = _paths.contracts_json
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _load_contracts_json() -> dict:
    return _load_contracts_json_cached(_file_mtime(_paths.contracts_json))


@lru_cache(maxsize=4)
def _load_product_master_cached(mtime: float) -> pd.DataFrame:
    path = _paths.product_master_csv
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _load_product_master() -> pd.DataFrame:
    return _load_product_master_cached(_file_mtime(_paths.product_master_csv))


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
    mtime_key = tuple(
        _file_mtime(_paths.processed / sys / symbol / f"{contract}.parquet")
        for sys in systems
    )
    return _load_contract_cached(symbol, contract, tuple(systems), mtime_key)


@lru_cache(maxsize=64)
def _load_contract_cached(
    symbol: str,
    contract: str,
    systems: tuple[str, ...],
    mtime_key: tuple[float, ...],
) -> pd.DataFrame:
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
    _load_contract_cached.cache_clear()
    _load_lookback_cached.cache_clear()
    _load_contracts_json_cached.cache_clear()
    _load_product_master_cached.cache_clear()
    _load_funnel_cached.cache_clear()


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


@lru_cache(maxsize=4)
def _load_funnel_cached(mtime: float) -> dict:
    path = _paths.funnel_json
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _load_funnel() -> dict:
    """Load `processed/_funnel.json`, re-reading whenever its mtime changes."""
    return _load_funnel_cached(_file_mtime(_paths.funnel_json))


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


def load_lookback(system: str, product: str) -> pd.DataFrame:
    """Load the per-system rolling 60-bar lookback for one product.

    Schema on disk: timestamp, contract, open, high, low, close, prob,
    Label_{N}. Returned frame is timestamp-indexed and column-normalized
    (open→Open, etc.) so chart code can reuse the OHLC convention.
    """
    path = _paths.lookback_dir(system) / f"{product}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No lookback parquet for {system}/{product}")
    return _load_lookback_cached(system, product, _file_mtime(path))


@lru_cache(maxsize=256)
def _load_lookback_cached(system: str, product: str, mtime: float) -> pd.DataFrame:
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


def load_latest_broker_state() -> BrokerState | None:
    """Read the broker-state snapshot embedded in the latest execution report."""
    state = load_latest_execution_report().get("broker_state")
    if not state:
        return None
    return _broker_state_from_json(state)


def load_position_rows() -> list[dict]:
    """Return dashboard rows for the latest broker positions.

    The dashboard treats the latest execution report as a run snapshot. IBKR
    remains the source of truth; this only renders what the latest run saw.
    """
    state = load_latest_broker_state()
    if state is None:
        return []

    reconciled = reconcile_state(state)
    rows: list[dict] = []

    for key, position in reconciled.positions_by_key.items():
        con_id, system = key
        stop = reconciled.protective_stops_by_key.get(key)
        rows.append(
            _position_row(
                position,
                status="held",
                system=system,
                side=SYSTEM_SIDE.get(system),
                stop_price=stop.aux_price if stop else None,
                stop_limit_price=stop.limit_price if stop else None,
                stop_order_id=stop.order_id if stop else None,
                stop_order_type=stop.order_type if stop else None,
                con_id=con_id,
                broker_state=state,
            )
        )

    for position in reconciled.positions_without_protective_stop:
        rows.append(
            _position_row(
                position,
                status="missing_stop",
                system=None,
                side=None,
                broker_state=state,
            )
        )

    for position in reconciled.unknown_system_positions:
        rows.append(
            _position_row(
                position,
                status="unknown_system",
                system=None,
                side=None,
                broker_state=state,
            )
        )

    status_order = {"held": 0, "missing_stop": 1, "unknown_system": 2}
    rows.sort(
        key=lambda row: (
            status_order.get(row["status"], 99),
            row.get("system") or "",
            row.get("symbol") or "",
            row.get("local_symbol") or "",
        )
    )
    return rows


def load_order_rows() -> list[dict]:
    """Return dashboard rows for open orders in the latest broker snapshot."""
    state = load_latest_broker_state()
    if state is None:
        return []

    position_conids = {position.con_id for position in state.positions}
    rows = [
        _order_row(order, position_conids=position_conids)
        for order in state.open_orders
    ]
    rows.sort(
        key=lambda row: (
            row.get("role") or "",
            row.get("system") or "",
            row.get("symbol") or "",
            row.get("local_symbol") or "",
            row.get("order_id") or 0,
        )
    )
    return rows


def load_fill_rows() -> list[dict]:
    """Return dashboard rows for recent fills in the latest broker snapshot."""
    state = load_latest_broker_state()
    if state is None:
        return []

    order_roles = _fill_order_roles(load_latest_execution_report())
    rows = [
        _fill_row(fill, order_roles=order_roles)
        for fill in state.recent_fills
    ]
    rows.sort(
        key=lambda row: (
            row.get("time") or "",
            row.get("order_id") or 0,
            row.get("exec_id") or "",
        ),
        reverse=True,
    )
    return rows


def _load_json(path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _position_row(
    position: BrokerPosition,
    *,
    status: str,
    system: str | None,
    side: str | None,
    stop_price: float | None = None,
    stop_limit_price: float | None = None,
    stop_order_id: int | None = None,
    stop_order_type: str | None = None,
    con_id: int | None = None,
    broker_state: BrokerState | None = None,
) -> dict:
    row_con_id = int(con_id if con_id is not None else position.con_id)
    estimated_last_day = _estimated_last_day(position.symbol, position.local_symbol)
    official_last_day = _official_last_day(
        row_con_id,
        broker_state,
        estimated_last_day,
    )
    entry_price = _position_entry_price(position)
    current_price = _position_current_price(position)
    multiplier, price_magnifier = _product_pricing(position.symbol)
    return {
        "status": status,
        "account": position.account,
        "con_id": row_con_id,
        "system": system,
        "side": side,
        "symbol": position.symbol,
        "local_symbol": position.local_symbol,
        "quantity": position.quantity,
        "avg_cost": position.avg_cost,
        "entry_price": entry_price,
        "entry_date": _position_entry_date(position, broker_state),
        "current_price": current_price,
        "market_price": position.market_price,
        "market_value": position.market_value,
        "unrealized_pnl": _position_unrealized_pnl(
            position,
            entry_price,
            current_price,
            multiplier,
            price_magnifier,
        ),
        "return_pct": _position_return_pct(position, entry_price, current_price),
        "current_risk": _position_current_risk(
            side,
            current_price,
            stop_price,
            position.quantity,
            multiplier,
            price_magnifier,
        ),
        "stop_price": stop_price,
        "stop_limit_price": stop_limit_price,
        "stop_order_id": stop_order_id,
        "stop_order_type": stop_order_type,
        "estimated_last_day": estimated_last_day,
        "official_last_day": official_last_day,
    }


def _order_row(order: BrokerOrder, *, position_conids: set[int]) -> dict:
    return {
        "role": _order_role(order, position_conids=position_conids),
        "order_id": order.order_id,
        "perm_id": order.perm_id,
        "con_id": order.con_id,
        "system": order.system,
        "symbol": order.symbol,
        "local_symbol": order.local_symbol,
        "action": str(order.action),
        "order_type": str(order.order_type),
        "quantity": order.quantity,
        "status": str(order.status),
        "aux_price": order.aux_price,
        "limit_price": order.limit_price,
        "parent_id": order.parent_id,
        "oca_group": order.oca_group,
        "oca_type": order.oca_type,
        "order_ref": order.order_ref,
        "tif": order.tif,
        "outside_rth": order.outside_rth,
        "transmit": order.transmit,
        "exchange": order.exchange,
        "currency": order.currency,
    }


def _order_role(order: BrokerOrder, *, position_conids: set[int]) -> str:
    side = _order_side(order)
    order_type = str(order.order_type)
    action = str(order.action)

    if (
        side is not None
        and action == side.entry_action
        and order_type in ENTRY_TYPES
    ):
        return "entry_orders"

    is_stop = order_type in STOP_TYPES
    if side is not None:
        is_stop = is_stop and action == side.protective_action
    if not is_stop:
        return "other_orders"

    if order.con_id in position_conids:
        return "current_position_stops"
    if order.parent_id is not None:
        return "entry_bracket_stops"
    return "old_position_stops"


def _order_side(order: BrokerOrder) -> Side | None:
    system = order.system
    if system not in SYSTEM_SIDE:
        return None
    try:
        return Side.from_config(SYSTEM_SIDE[system])
    except ValueError:
        return None


def _fill_order_roles(report: dict) -> dict[int, str]:
    roles: dict[int, str] = {}
    for record in report.get("submitted", []):
        status = str(record.get("status") or "")
        if status == "submitted":
            order_ids = [
                _optional_int(order_id)
                for order_id in record.get("order_ids", [])
            ]
            order_ids = [
                order_id for order_id in order_ids if order_id is not None
            ]
            if order_ids:
                roles[order_ids[0]] = "entry_fills"
                for order_id in order_ids[1:]:
                    roles[order_id] = "exit_fills"
        elif status == "exit_submitted":
            order_id = _optional_int(record.get("order_id"))
            if order_id is not None:
                roles[order_id] = "exit_fills"
        elif status == "roll_submitted":
            for key in ("closeout_order_ids", "roll_order_ids"):
                for order_id in record.get(key, []):
                    parsed = _optional_int(order_id)
                    if parsed is not None:
                        roles[parsed] = "roll_fills"
    return roles


def _fill_row(fill: BrokerFill, *, order_roles: dict[int, str]) -> dict:
    system = VOICE_TO_SYSTEM.get(fill.order_ref or "")
    role = order_roles.get(fill.order_id) or _fill_role_from_side(fill, system)
    return {
        "role": role,
        "exec_id": fill.exec_id,
        "order_id": fill.order_id,
        "con_id": fill.con_id,
        "system": system,
        "symbol": fill.symbol,
        "local_symbol": fill.local_symbol,
        "side": fill.side,
        "quantity": fill.quantity,
        "price": fill.price,
        "time": fill.time,
        "order_ref": fill.order_ref,
        "classification": (
            "latest_run_order_id"
            if fill.order_id in order_roles
            else "order_ref_side"
            if role != "other_fills"
            else "unclassified"
        ),
    }


def _fill_role_from_side(fill: BrokerFill, system: str | None) -> str:
    if system not in SYSTEM_SIDE:
        return "other_fills"
    try:
        side = Side.from_config(SYSTEM_SIDE[system])
    except ValueError:
        return "other_fills"
    action = _fill_action(fill.side)
    if action == side.entry_action:
        return "entry_fills"
    if action == side.exit_action:
        return "exit_fills"
    return "other_fills"


def _fill_action(side: str) -> str:
    side = str(side or "").upper()
    if side in {"BOT", "BUY", "BOUGHT"}:
        return "BUY"
    if side in {"SLD", "SELL", "SOLD"}:
        return "SELL"
    return side


def _position_entry_price(position: BrokerPosition) -> float:
    multiplier, price_magnifier = _product_pricing(position.symbol)
    if multiplier <= 0:
        return float(position.avg_cost)
    return float(position.avg_cost) / multiplier * price_magnifier


def _product_pricing(symbol: str) -> tuple[float, int]:
    pm = _load_product_master()
    if pm.empty or "symbol" not in pm.columns:
        return 1.0, 1
    row = pm[pm["symbol"] == symbol]
    if row.empty:
        return 1.0, 1
    r = row.iloc[0]
    multiplier = _positive_float(r.get("multiplier"), 1.0)
    price_magnifier = int(_positive_float(r.get("priceMagnifier"), 1.0))
    return multiplier, price_magnifier


def _positive_float(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(number) or number <= 0:
        return default
    return number


def _position_current_price(position: BrokerPosition) -> float | None:
    if position.market_price is not None:
        return float(position.market_price)
    try:
        df = load_contract(position.symbol, position.local_symbol)
    except Exception:
        return None
    if "Settle" not in df.columns:
        return None
    settle = df["Settle"].dropna()
    if settle.empty:
        return None
    return float(settle.iloc[-1])


def _position_unrealized_pnl(
    position: BrokerPosition,
    entry_price: float | None,
    current_price: float | None,
    multiplier: float,
    price_magnifier: int,
) -> float | None:
    if entry_price is None or current_price is None:
        return None
    if multiplier <= 0 or price_magnifier <= 0:
        return None
    return (
        (current_price - entry_price)
        / price_magnifier
        * multiplier
        * position.quantity
    )


def _position_return_pct(
    position: BrokerPosition,
    entry_price: float | None,
    current_price: float | None,
) -> float | None:
    if entry_price is None or current_price is None or entry_price <= 0:
        return None
    if position.quantity == 0:
        return None
    direction = 1 if position.quantity > 0 else -1
    return (current_price - entry_price) / entry_price * direction


def _position_current_risk(
    side: str | None,
    current_price: float | None,
    stop_price: float | None,
    quantity: float,
    multiplier: float,
    price_magnifier: int,
) -> float | None:
    if side is None or current_price is None or stop_price is None:
        return None
    try:
        return calculate_position_risk(
            side=side,
            current_price=current_price,
            stop_price=stop_price,
            quantity=quantity,
            multiplier=multiplier,
            price_magnifier=price_magnifier,
        )
    except (TypeError, ValueError):
        return None


def _position_entry_date(
    position: BrokerPosition,
    broker_state: BrokerState | None,
) -> date | None:
    if broker_state is None:
        return None
    expected_side = "BOT" if position.quantity > 0 else "SLD"
    fills = [f for f in broker_state.recent_fills if f.con_id == position.con_id]
    side_matches = [f for f in fills if str(f.side).upper() == expected_side]
    candidates = side_matches or fills
    parsed = [_parse_fill_date(fill.time) for fill in candidates]
    parsed = [d for d in parsed if d is not None]
    return min(parsed) if parsed else None


def _parse_fill_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) >= 8 and raw[:8].isdigit():
        try:
            return datetime.strptime(raw[:8], "%Y%m%d").date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _estimated_last_day(symbol: str, local_symbol: str) -> date | None:
    dates = get_contract_dates(symbol, local_symbol)
    return dates.last_day.date() if dates.last_day is not None else None


def _official_last_day(
    con_id: int,
    broker_state: BrokerState | None,
    estimated_last_day: date | None,
) -> date | None:
    if broker_state is None or estimated_last_day is None:
        return None
    next_rth_day = broker_state.next_rth_days.get(con_id)
    if next_rth_day is None or next_rth_day < estimated_last_day:
        return None
    return next_rth_day


def _broker_state_from_json(data: dict) -> BrokerState:
    account_data = data.get("account") or {}
    return BrokerState(
        collected_at=_parse_datetime(data.get("collected_at")),
        account=AccountState(
            net_liquidation=float(account_data.get("net_liquidation", 0.0) or 0.0),
            currency=str(account_data.get("currency", "USD") or "USD"),
            account_id=account_data.get("account_id"),
            buying_power=_optional_float(account_data.get("buying_power")),
            raw_values=account_data.get("raw_values") or {},
        ),
        positions=[_broker_position_from_json(p) for p in data.get("positions", [])],
        open_orders=[_broker_order_from_json(o) for o in data.get("open_orders", [])],
        recent_fills=[_broker_fill_from_json(f) for f in data.get("recent_fills", [])],
        next_rth_days=_next_rth_days_from_json(data.get("next_rth_days") or {}),
        contract_meta=_contract_meta_from_json(data.get("contract_meta") or {}),
    )


def _broker_position_from_json(data: dict) -> BrokerPosition:
    return BrokerPosition(
        account=str(data.get("account", "") or ""),
        con_id=int(data.get("con_id", 0) or 0),
        symbol=str(data.get("symbol", "") or ""),
        local_symbol=str(data.get("local_symbol", "") or ""),
        quantity=float(data.get("quantity", 0.0) or 0.0),
        avg_cost=float(data.get("avg_cost", 0.0) or 0.0),
        market_price=_optional_float(data.get("market_price")),
        market_value=_optional_float(data.get("market_value")),
    )


def _broker_order_from_json(data: dict) -> BrokerOrder:
    return BrokerOrder(
        order_id=int(data.get("order_id", 0) or 0),
        con_id=int(data.get("con_id", 0) or 0),
        symbol=str(data.get("symbol", "") or ""),
        local_symbol=str(data.get("local_symbol", "") or ""),
        action=str(data.get("action", "") or ""),
        order_type=str(data.get("order_type", "") or ""),
        quantity=int(float(data.get("quantity", 0) or 0)),
        status=str(data.get("status", "Unknown") or "Unknown"),
        exchange=str(data.get("exchange", "") or ""),
        currency=str(data.get("currency", "") or ""),
        system=data.get("system"),
        aux_price=_optional_float(data.get("aux_price")),
        limit_price=_optional_float(data.get("limit_price")),
        parent_id=_optional_int(data.get("parent_id")),
        perm_id=_optional_int(data.get("perm_id")),
        oca_group=data.get("oca_group"),
        oca_type=_optional_int(data.get("oca_type")),
        order_ref=data.get("order_ref"),
        tif=data.get("tif"),
        outside_rth=data.get("outside_rth"),
        transmit=data.get("transmit"),
    )


def _broker_fill_from_json(data: dict) -> BrokerFill:
    return BrokerFill(
        exec_id=str(data.get("exec_id", "") or ""),
        order_id=int(data.get("order_id", 0) or 0),
        con_id=int(data.get("con_id", 0) or 0),
        symbol=str(data.get("symbol", "") or ""),
        local_symbol=str(data.get("local_symbol", "") or ""),
        side=str(data.get("side", "") or ""),
        quantity=int(float(data.get("quantity", 0) or 0)),
        price=float(data.get("price", 0.0) or 0.0),
        time=str(data.get("time", "") or ""),
        order_ref=data.get("order_ref"),
    )


def _contract_meta_from_json(data: dict) -> dict[int, ContractMeta]:
    out: dict[int, ContractMeta] = {}
    for key, value in data.items():
        try:
            con_id = int(key)
        except (TypeError, ValueError):
            continue
        out[con_id] = ContractMeta(
            con_id=int(value.get("con_id", con_id) or con_id),
            symbol=str(value.get("symbol", "") or ""),
            local_symbol=str(value.get("local_symbol", "") or ""),
            exchange=str(value.get("exchange", "") or ""),
            currency=str(value.get("currency", "") or ""),
            multiplier=float(value.get("multiplier", 1.0) or 1.0),
            min_tick=float(value.get("min_tick", 0.0) or 0.0),
            price_magnifier=int(float(value.get("price_magnifier", 1) or 1)),
            last_trade_date=_parse_date_value(value.get("last_trade_date")),
            last_day=_parse_date_value(value.get("last_day")),
        )
    return out


def _parse_datetime(value) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.min


def _parse_date_value(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _next_rth_days_from_json(data: dict) -> dict[int, date]:
    out = {}
    for con_id, value in data.items():
        parsed = _parse_date_value(value)
        if parsed is not None:
            out[int(con_id)] = parsed
    return out


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
