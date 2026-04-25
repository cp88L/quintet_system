"""Data path management for quintet."""

from pathlib import Path


class DataPaths:
    """Manages quintet data directory paths."""

    def __init__(self, base_dir: Path | str | None = None):
        """
        Initialize data paths.

        Args:
            base_dir: Base data directory. Defaults to this module's directory.
        """
        if base_dir is None:
            self.base = Path(__file__).parent
        else:
            self.base = Path(base_dir)

        self.reference = self.base / "reference"
        self.raw = self.base / "raw"
        self.processed = self.base / "processed"

    @property
    def product_master_csv(self) -> Path:
        """Path to ibkr_product_master.csv."""
        return self.reference / "ibkr_product_master.csv"

    @property
    def contracts_json(self) -> Path:
        """Path to futures_contracts_2021_2027.json."""
        return self.reference / "futures_contracts_2021_2027.json"

    @property
    def positions_json(self) -> Path:
        """Path to open_positions.json."""
        return self.reference / "open_positions.json"

    @property
    def orders_json(self) -> Path:
        """Path to open_orders.json."""
        return self.reference / "open_orders.json"

    @property
    def rejections_json(self) -> Path:
        """Path to order_rejections.json."""
        return self.reference / "order_rejections.json"

    @property
    def manual_labels_json(self) -> Path:
        """Path to manual_labels.json (user-maintained label overrides)."""
        return self.reference / "manual_labels.json"

    def raw_dir(self, symbol: str) -> Path:
        """
        Get raw data directory for a symbol, creating if needed.

        Args:
            symbol: Product symbol (e.g., 'GC', 'ES')

        Returns:
            Path to raw/{symbol}/
        """
        path = self.raw / symbol
        path.mkdir(parents=True, exist_ok=True)
        return path

    def processed_dir(self, symbol: str) -> Path:
        """
        Get processed data directory for a symbol, creating if needed.

        Args:
            symbol: Product symbol (e.g., 'GC', 'ES')

        Returns:
            Path to processed/{symbol}/
        """
        path = self.processed / symbol
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_dirs(self) -> None:
        """Create base raw/ and processed/ directories."""
        self.raw.mkdir(parents=True, exist_ok=True)
        self.processed.mkdir(parents=True, exist_ok=True)

    def ensure_product_dirs(self, symbols: list[str]) -> None:
        """
        Create raw/ and processed/ subdirectories for all symbols.

        Args:
            symbols: List of product symbols
        """
        for symbol in symbols:
            self.raw_dir(symbol)
            self.processed_dir(symbol)
