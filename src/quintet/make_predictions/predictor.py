"""Generate XGBoost probability predictions for processed contracts."""

from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from quintet.config import (
    MODELS_DIR,
    SYSTEM_LABEL,
    SYSTEM_SIDE,
    SYSTEM_UNIVERSE,
)
from quintet.contract_handler.product_master import ProductMaster
from quintet.data.paths import DataPaths


def _model_path(system: str) -> Path:
    """Resolve the model JSON path for a system."""
    fname = (
        f"label_{SYSTEM_LABEL[system]}_"
        f"{SYSTEM_UNIVERSE[system]}_{SYSTEM_SIDE[system]}_model.json"
    )
    return MODELS_DIR / fname


class ContractPredictor:
    """Score processed parquets with each system's XGBoost model."""

    def __init__(self, paths: DataPaths | None = None, master: ProductMaster | None = None):
        self.paths = paths or DataPaths()
        if master is None:
            master = ProductMaster(self.paths.product_master_csv)
            master.load()
        self.master = master
        self._boosters: dict[str, xgb.Booster] = {}

    def _booster(self, system: str) -> xgb.Booster:
        if system not in self._boosters:
            booster = xgb.Booster()
            booster.load_model(_model_path(system))
            self._boosters[system] = booster
        return self._boosters[system]

    def predict(self, df: pd.DataFrame, system: str) -> pd.Series:
        """Return a Series of probabilities aligned to df.index, NaN during warmup."""
        booster = self._booster(system)
        features = list(booster.feature_names)

        missing = [f for f in features if f not in df.columns]
        if missing:
            raise ValueError(f"Missing features for {system}: {missing}")

        valid = df[features].notna().all(axis=1)
        probs = np.full(len(df), np.nan)
        if valid.any():
            dmatrix = xgb.DMatrix(df.loc[valid, features], feature_names=features)
            probs[valid.values] = booster.predict(dmatrix)
        return pd.Series(probs, index=df.index, name='prob')

    def process_file(self, parquet_path: Path, system: str) -> pd.DataFrame:
        """Read parquet, add `prob` column, write back in place."""
        df = pd.read_parquet(parquet_path)
        df['prob'] = self.predict(df, system)
        df.to_parquet(parquet_path, index=False)
        return df

    def process_symbol(self, system: str, symbol: str) -> int:
        """Score every parquet under processed/{system}/{symbol}/."""
        symbol_dir = self.paths.processed / system / symbol
        if not symbol_dir.exists():
            return 0
        count = 0
        for parquet_file in sorted(symbol_dir.glob("*.parquet")):
            self.process_file(parquet_file, system)
            count += 1
        return count

    def process_system(
        self,
        system: str,
        active_locals: set[str] | None = None,
    ) -> dict[str, int]:
        """Score products in the system's universe with one batch predict.

        Reads every parquet under processed/{system}/, concatenates their
        feature rows into a single DMatrix, calls booster.predict once, and
        scatters the result back to each parquet's `prob` column. When
        `active_locals` is provided, only parquets whose stem is in that set
        are re-scored.
        """
        booster = self._booster(system)
        features = list(booster.feature_names)

        parquet_paths: list[Path] = []
        for symbol in self.master.get_products_for_system(system):
            symbol_dir = self.paths.processed / system / symbol
            if not symbol_dir.exists():
                continue
            parquet_paths.extend(sorted(symbol_dir.glob("*.parquet")))

        if active_locals is not None:
            parquet_paths = [p for p in parquet_paths if p.stem in active_locals]

        if not parquet_paths:
            return {}

        dfs = [pd.read_parquet(p) for p in parquet_paths]
        masks = [df[features].notna().all(axis=1) for df in dfs]

        combined = pd.concat(
            [df.loc[m, features] for df, m in zip(dfs, masks)],
            ignore_index=True,
        )
        if combined.empty:
            all_probs = np.array([])
        else:
            dmatrix = xgb.DMatrix(combined, feature_names=features)
            all_probs = booster.predict(dmatrix)

        cursor = 0
        results: dict[str, int] = {}
        for path, df, mask in zip(parquet_paths, dfs, masks):
            n_valid = int(mask.sum())
            probs = np.full(len(df), np.nan)
            if n_valid:
                probs[mask.values] = all_probs[cursor:cursor + n_valid]
                cursor += n_valid
            df['prob'] = probs
            df.to_parquet(path, index=False)
            symbol = path.parent.name
            results[symbol] = results.get(symbol, 0) + 1
        return results
