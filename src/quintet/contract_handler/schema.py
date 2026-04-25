"""Data models for contract and product information."""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class ScanWindow:
    """Represents the scan window for a contract."""

    start_scan: Optional[date]
    end_scan: date
    last_day: date


@dataclass(frozen=True)
class ContractInfo:
    """Individual futures contract information."""

    local_symbol: str
    con_id: int
    exchange: str
    contract_month: str  # YYYYMM format
    scan_window: ScanWindow
    last_trade_date: date


@dataclass(frozen=True)
class ProductConfig:
    """Product configuration from master CSV."""

    symbol: str
    exchange: str
    trading_class: str
    currency: str
    multiplier: float
    long_name: str
    min_tick: float
    price_magnifier: int
    timezone_id: str
    active_months: list[int]
    last_month: int
    last_day_offset: int
    buffer: int
    hourly: bool
    active: bool
    systems: frozenset[str]


