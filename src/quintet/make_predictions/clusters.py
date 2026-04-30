"""Cross-sectional cluster assignment for today's per-product strength.

For each system with `N_CLUSTERS[s]` not None, the cluster step:

1. For each product P in the system universe, finds the registry contract
   C whose scan window covers today (`start_scan(C) <= today <=
   end_scan(C)`). Scan window is the entry gate; nothing else.
2. Reads C's parquet and records its last bar date per product. Today =
   max(last_bar) across the system. Products whose last bar < today are
   reported as misaligned.
3. Takes `VNS_{SYSTEM_LABEL[s]}` from C's today row for each product.
4. Clusters those values with `whiten / kmeans / vq` using a fixed RNG so
   repeated EOD runs over the same data produce the same labels. Cluster 0 =
   weakest centroid.

Returns a dict with today's labels per product. The result is consumed
in-process; nothing is written to disk.
"""

from datetime import date as date_cls

import numpy as np
import pandas as pd
from scipy.cluster.vq import kmeans, vq, whiten

from quintet.config import N_CLUSTERS, SYSTEM_LABEL
from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.product_master import ProductMaster
from quintet.data.paths import DataPaths


class ClusterAssigner:
    """Single-date k-means clustering of the strength feature per system."""

    def __init__(
        self,
        paths: DataPaths | None = None,
        master: ProductMaster | None = None,
        registry: ContractRegistry | None = None,
    ):
        self.paths = paths or DataPaths()
        if master is None:
            master = ProductMaster(self.paths.product_master_csv)
            master.load()
        self.master = master
        if registry is None:
            registry = ContractRegistry(self.paths.contracts_json)
            registry.load()
        self.registry = registry

    def process_system(self, system: str) -> dict | None:
        """Cluster today's universe for `system`. Returns a summary dict.

        Returns None if `N_CLUSTERS[system]` is None (filter disabled).
        """
        n = N_CLUSTERS[system]
        if n is None:
            return None

        strength_col = f"VNS_{SYSTEM_LABEL[system]}"
        today_clk = pd.Timestamp(date_cls.today())

        # Pass 1: for each product, find the scan-window-active contract
        # for today's date and record its last bar.
        in_scan: dict[str, dict] = {}
        for symbol in self.master.get_products_for_system(system):
            symbol_dir = self.paths.processed / system / symbol
            if not symbol_dir.exists():
                continue
            for c in self.registry.get_contracts_for_product(symbol).values():
                sw = c.scan_window
                if sw.start_scan is None:
                    continue
                start = pd.Timestamp(sw.start_scan)
                end = pd.Timestamp(sw.end_scan)
                if not (start <= today_clk <= end):
                    continue
                path = symbol_dir / f"{c.local_symbol}.parquet"
                if not path.exists():
                    break
                df = pd.read_parquet(path)
                if len(df) == 0:
                    break
                in_scan[symbol] = {
                    "local_symbol": c.local_symbol,
                    "path": path,
                    "df": df,
                    "last_bar": df["timestamp"].dt.normalize().max(),
                }
                break  # one scan-window contract per product

        if not in_scan:
            return {
                "system": system,
                "today": None,
                "n_in_scan": 0,
                "n_products": 0,
                "misaligned": [],
                "skipped_reason": "no_observations",
                "std": None,
                "centroids_w": None,
                "centroids_r": None,
                "labels_by_product": None,
            }

        today = max(d["last_bar"] for d in in_scan.values())
        misaligned = sorted(
            (sym, d["local_symbol"], d["last_bar"])
            for sym, d in in_scan.items()
            if d["last_bar"] != today
        )

        # Pass 2: build today's cross-section from in-scan contracts only.
        strengths: dict[str, float] = {}
        for sym, d in in_scan.items():
            df = d["df"]
            if strength_col not in df.columns:
                continue
            dates = df["timestamp"].dt.normalize()
            match = (dates == today).values
            if not match.any():
                continue
            row_idx = int(np.flatnonzero(match)[0])
            s = df[strength_col].iat[row_idx]
            if pd.isna(s):
                continue
            strengths[sym] = float(s)

        n_products = len(strengths)
        result: dict = {
            "system": system,
            "today": today,
            "n_in_scan": len(in_scan),
            "n_products": n_products,
            "misaligned": misaligned,
            "skipped_reason": None,
            "std": None,
            "centroids_w": None,
            "centroids_r": None,
            "labels_by_product": None,
        }

        if n_products == 0:
            result["skipped_reason"] = "no_observations"
            return result
        if sum(strengths.values()) == 0.0:
            result["skipped_reason"] = "zero_strength"
            return result
        if n_products < n:
            result["skipped_reason"] = "too_few"
            return result

        products = list(strengths.keys())
        arr = np.array([strengths[p] for p in products], dtype=np.float64)

        # ddof=0 to match scipy.cluster.vq.whiten's std divisor.
        std = arr.std()
        if std == 0.0:
            raise RuntimeError(
                f"{system}: degenerate VNS universe on "
                f"{pd.Timestamp(today).date()} — all {n_products} "
                f"products have {strength_col} = {arr[0]}. "
                "Cannot cluster zero-variance input."
            )

        w = whiten(arr)
        centroids, _ = kmeans(w, n, rng=np.random.default_rng(0))
        sorted_centroids = np.sort(centroids)  # cluster 0 = weakest
        labels, _ = vq(w, sorted_centroids)

        result["std"] = float(std)
        result["centroids_w"] = sorted_centroids.tolist()
        result["centroids_r"] = (sorted_centroids * std).tolist()
        result["labels_by_product"] = {p: int(l) for p, l in zip(products, labels)}

        return result
