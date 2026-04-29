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

    def processed_dir(self, system: str, symbol: str) -> Path:
        """
        Get processed data directory for a (subsystem, symbol), creating if needed.

        Args:
            system: Subsystem alias (e.g., 'C4', 'CS4', 'E4', 'E7', 'E13')
            symbol: Product symbol (e.g., 'GC', 'ES')

        Returns:
            Path to processed/{system}/{symbol}/
        """
        path = self.processed / system / symbol
        path.mkdir(parents=True, exist_ok=True)
        return path

    def lookback_dir(self, system: str) -> Path:
        """
        Get the per-system tau-lookback directory, creating if needed.

        Returns Path to processed/{system}/_lookback/. One parquet per
        product holds the rolling 60-bar (timestamp, contract, OHLC, prob,
        Label_{N}) pool used by the Wilson tau walkdown.
        """
        path = self.processed / system / "_lookback"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def tau_json_path(self, system: str) -> Path:
        """Path to processed/{system}/_tau.json holding the per-system tau snapshot."""
        return self.processed / system / "_tau.json"

    @property
    def funnel_json(self) -> Path:
        """Path to processed/_funnel.json — combined per-system funnel snapshot."""
        return self.processed / "_funnel.json"

    def ensure_dirs(self) -> None:
        """Create base raw/ and processed/ directories."""
        self.raw.mkdir(parents=True, exist_ok=True)
        self.processed.mkdir(parents=True, exist_ok=True)

    def ensure_product_dirs(self, system: str, symbols: list[str]) -> None:
        """
        Create raw/ and processed/{system}/ subdirectories for all symbols.

        Args:
            system: Subsystem alias (e.g., 'C4')
            symbols: List of product symbols
        """
        for symbol in symbols:
            self.raw_dir(symbol)
            self.processed_dir(system, symbol)
