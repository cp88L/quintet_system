"""Product master CSV loader."""

from pathlib import Path

import pandas as pd

from quintet.config import SYSTEMS
from quintet.contract_handler.schema import ProductConfig


class ProductMaster:
    """Loads and provides access to product master configuration."""

    def __init__(self, csv_path: Path | str):
        self._csv_path = Path(csv_path)
        self._products: dict[str, ProductConfig] = {}
        self._loaded = False

    def load(self) -> None:
        """Load product master CSV into memory."""
        df = pd.read_csv(self._csv_path)
        for _, row in df.iterrows():
            systems = frozenset(
                system for system in SYSTEMS
                if int(row[system.lower()]) == 1
            )
            config = ProductConfig(
                symbol=row["symbol"],
                exchange=row["exchange"],
                trading_class=row["tradingClass"],
                currency=row["currency"],
                multiplier=float(row["multiplier"]),
                long_name=row["longName"],
                min_tick=float(row["minTick"]),
                price_magnifier=int(row["priceMagnifier"]),
                timezone_id=row["timeZoneId"],
                active_months=[int(m) for m in str(row["active_months"]).split(",") if m.strip()],
                last_month=int(row["last_month"]),
                last_day_offset=int(row["last_day"]),
                buffer=int(row["buffer"]),
                hourly=bool(int(row["hourly"])),
                active=bool(int(row["active"])),
                systems=systems,
            )
            self._products[config.symbol] = config
        self._loaded = True

    def get_active_products(self) -> dict[str, ProductConfig]:
        """Get all products where active=True."""
        if not self._loaded:
            raise RuntimeError("ProductMaster not loaded. Call load() first.")
        return {k: v for k, v in self._products.items() if v.active}

    def get_products_for_system(self, system: str) -> dict[str, ProductConfig]:
        """Get active products participating in the given subsystem (e.g., 'C4')."""
        if not self._loaded:
            raise RuntimeError("ProductMaster not loaded. Call load() first.")
        if system not in SYSTEMS:
            raise ValueError(f"Unknown system {system!r}. Expected one of {SYSTEMS}.")
        return {
            k: v for k, v in self._products.items()
            if v.active and system in v.systems
        }

    def get_product(self, symbol: str) -> ProductConfig | None:
        """Get product config by symbol."""
        if not self._loaded:
            raise RuntimeError("ProductMaster not loaded. Call load() first.")
        return self._products.get(symbol)
