"""Process raw contract data and add per-subsystem indicators.

Output layout: data/processed/{system}/{symbol}/{local_symbol}.parquet
Each parquet carries OHLCV plus the indicators listed in INDICATORS[system],
in that order.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from quintet.config import INDICATORS, INTRADAY_CUTOFF_HOUR
from quintet.contract_handler.product_master import ProductMaster
from quintet.data.paths import DataPaths
from quintet.process_contracts.indicators import Indicators


OHLCV = ["timestamp", "open", "high", "low", "close", "volume"]


class ContractProcessor:
    """Process raw contract CSV files into per-subsystem parquet."""

    def __init__(self, paths: DataPaths | None = None, master: ProductMaster | None = None):
        self.paths = paths or DataPaths()
        if master is None:
            master = ProductMaster(self.paths.product_master_csv)
            master.load()
        self.master = master

    @staticmethod
    def _is_hourly_data(df: pd.DataFrame) -> bool:
        if len(df) < 2:
            return False
        dates = df['timestamp'].dt.date
        return dates.duplicated().any()

    @staticmethod
    def _aggregate_hourly_to_daily(
        df: pd.DataFrame, cutoff_hour: int = INTRADAY_CUTOFF_HOUR
    ) -> pd.DataFrame:
        """Aggregate intraday OHLCV to daily bars with a custom day boundary.

        Bars before cutoff_hour are bucketed into the previous trading day.
        """
        if df.empty:
            return df

        working = df.copy()
        working['datetime'] = pd.to_datetime(working['timestamp']).dt.tz_localize(None)

        shifted = working['datetime'] - pd.Timedelta(hours=cutoff_hour)
        working['__group'] = shifted.dt.floor('D')

        aggregations = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        if 'volume' in working.columns:
            aggregations['volume'] = 'sum'

        grouped = working.groupby('__group').agg(aggregations).reset_index()
        grouped['timestamp'] = grouped['__group'] + pd.Timedelta(hours=cutoff_hour)
        grouped = grouped.drop(columns=['__group'])

        cols = ['timestamp', 'open', 'high', 'low', 'close']
        if 'volume' in grouped.columns:
            cols.append('volume')
        return grouped[cols].sort_values('timestamp').reset_index(drop=True)

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        system: str,
        asof: date | None = None,
    ) -> pd.DataFrame:
        """Read raw CSV, compute indicators for `system`, write slim parquet.

        When `asof` is provided, rows whose date is >= `asof` are dropped
        before any aggregation or indicator computation — used in dev to
        strip today's still-open partial bar.
        """
        df = pd.read_csv(input_path, parse_dates=["timestamp"])
        if asof is not None:
            df = df[df["timestamp"].dt.normalize() < pd.Timestamp(asof)]
        if self._is_hourly_data(df):
            df = self._aggregate_hourly_to_daily(df)

        # Indicators expect Open/High/Low/Settle/Volume; raw uses lowercase.
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Settle',
            'volume': 'Volume',
        })

        for col in INDICATORS[system]:
            family, _, window_str = col.partition("_")
            window = int(window_str)
            if family == "Sup":
                df[col] = Indicators.support(df, window)
            elif family == "Res":
                df[col] = Indicators.resistance(df, window)
            elif family == "sEMA":
                df[col] = Indicators.calculate_sema(df, window)
            elif family == "nATR":
                df[col] = Indicators.calculate_natr(df, window)
            elif family == "VNS":
                df[col] = Indicators.calculate_vns(df, window)
            elif family == "Mo":
                df[col] = Indicators.calculate_mo(df, window)
            elif family == "RSpos":
                df[col] = Indicators.calculate_rs_pos(df, window)
            else:
                raise ValueError(f"Unknown indicator {col!r}")

        # Restore lowercase OHLCV for output, keep indicator columns as-is.
        df = df.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Settle': 'close',
            'Volume': 'volume',
        })

        out_cols = [c for c in OHLCV + list(INDICATORS[system]) if c in df.columns]
        df = df[out_cols]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        return df

    def process_symbol(
        self,
        system: str,
        symbol: str,
        active_locals: set[str] | None = None,
        asof: date | None = None,
    ) -> int:
        """Process every raw CSV for `symbol` into processed/{system}/{symbol}/.

        Prunes any processed parquets whose raw CSV no longer exists, keeping
        the processed dir as a strict mirror of the raw dir. When
        `active_locals` is provided, only CSVs whose stem is in that set are
        (re)processed; existing parquets for inactive contracts are left
        untouched. `asof` is forwarded to `process_file`.
        """
        raw_dir = self.paths.raw / symbol
        if not raw_dir.exists():
            return 0

        processed_dir = self.paths.processed_dir(system, symbol)
        raw_stems = {p.stem for p in raw_dir.glob("*.csv")}
        for parquet_file in processed_dir.glob("*.parquet"):
            if parquet_file.stem not in raw_stems:
                parquet_file.unlink()

        count = 0
        for csv_file in sorted(raw_dir.glob("*.csv")):
            if active_locals is not None and csv_file.stem not in active_locals:
                continue
            output_file = processed_dir / (csv_file.stem + ".parquet")
            self.process_file(csv_file, output_file, system=system, asof=asof)
            count += 1
        return count

    def process_system(
        self,
        system: str,
        active_locals: set[str] | None = None,
        asof: date | None = None,
    ) -> dict[str, int]:
        """Process products in `system`'s universe. Returns symbol → file count.

        See `process_symbol` for `active_locals` semantics. `asof` is
        forwarded to `process_file`.
        """
        results: dict[str, int] = {}
        for symbol in self.master.get_products_for_system(system):
            count = self.process_symbol(
                system, symbol, active_locals=active_locals, asof=asof
            )
            if count > 0:
                results[symbol] = count
        return results
