"""Contract registry for loading and querying futures contracts from JSON."""

import json
from datetime import date, datetime
from pathlib import Path

from quintet.contract_handler.schema import ContractInfo, ScanWindow


class ContractRegistry:
    """Loads and manages futures contract data from JSON."""

    def __init__(self, json_path: Path | str):
        self._json_path = Path(json_path)
        self._data: dict = {}
        self._loaded = False

    def load(self) -> None:
        """Load contracts JSON into memory."""
        with open(self._json_path) as f:
            self._data = json.load(f)
        self._loaded = True

    def get_contracts_for_product(self, symbol: str) -> dict[str, ContractInfo]:
        """Get all contracts for a product."""
        self._ensure_loaded()
        product = self._data.get("products", {}).get(symbol)
        if not product:
            return {}
        return {month: self._parse_contract(data) for month, data in product.get("contracts", {}).items()}

    def is_product_active(self, symbol: str) -> bool:
        """Check if a product is marked as active in the JSON."""
        self._ensure_loaded()
        product = self._data.get("products", {}).get(symbol)
        return product.get("active", False) if product else False

    def get_active_contract(self, symbol: str, as_of: date | None = None) -> str | None:
        """Get the contract currently in scan window for a product.

        Args:
            symbol: Product symbol (e.g., 'GC', 'ES')
            as_of: Date to check against. Defaults to today.

        Returns:
            Local symbol (e.g., 'GCG6') or None if no contract in scan
        """
        if as_of is None:
            as_of = date.today()

        contracts = self.get_contracts_for_product(symbol)
        for contract in contracts.values():
            sw = contract.scan_window
            if sw.start_scan and sw.start_scan <= as_of <= sw.end_scan:
                return contract.local_symbol
        return None

    def get_active_symbols(self) -> list[str]:
        """Get all active product symbols."""
        self._ensure_loaded()
        products = self._data.get("products", {})
        return [sym for sym, data in products.items() if data.get("active", False)]

    def get_contract_by_con_id(self, con_id: int) -> ContractInfo | None:
        """Get contract info by IBKR con_id.

        Searches all products for a contract with matching con_id.

        Args:
            con_id: IBKR contract ID

        Returns:
            ContractInfo if found, None otherwise
        """
        self._ensure_loaded()
        products = self._data.get("products", {})
        for symbol in products:
            contracts = self.get_contracts_for_product(symbol)
            for contract in contracts.values():
                if contract.con_id == con_id:
                    return contract
        return None

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("ContractRegistry not loaded. Call load() first.")

    @staticmethod
    def _parse_contract(data: dict) -> ContractInfo:
        """Parse raw contract dict into ContractInfo."""
        start_scan_str = data.get("start_scan", "")
        start_scan = datetime.strptime(start_scan_str, "%Y-%m-%d").date() if start_scan_str else None
        end_scan = datetime.strptime(data["end_scan"], "%Y-%m-%d").date()
        last_day = datetime.strptime(data["last_day"], "%Y-%m-%d").date()

        last_trade_str = data.get("lastTradeDateOrContractMonth", "")
        last_trade_date = (
            datetime.strptime(last_trade_str[:8], "%Y%m%d").date()
            if last_trade_str and len(last_trade_str) >= 8
            else last_day
        )

        return ContractInfo(
            local_symbol=data["localSymbol"],
            con_id=data["conId"],
            exchange=data["exchange"],
            contract_month=data["contractMonth"],
            scan_window=ScanWindow(start_scan=start_scan, end_scan=end_scan, last_day=last_day),
            last_trade_date=last_trade_date,
        )
