"""Wilson lower-bound threshold (tau) for per-system live signal gating.

Replicates the algorithm in
`/home/cp/dev/data_pipeline/notebooks/final_equities_4.ipynb:558-595` and
`:687-731`. For each system, today's tau is computed by pooling every
product's 60-bar (prob, Label) lookback into one array, then walking
down sorted-by-prob and finding the deepest k where the Wilson lower
bound at confidence (1 - WILSON_ALPHA) still meets PRECISION[system].

Differences from the notebook:
- No `MAX_CONTRACTS` cap. We rely on the lookback builder's natural
  termination (60 bars accumulated).
- No `DEFAULT_TAU` fallback. If the walkdown finds no valid k, tau is
  NaN and the system produces no signal that day.
"""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import norm

from quintet.config import (
    LOOKBACK_WINDOW,
    PRECISION,
    SYSTEM_LABEL,
    WILSON_ALPHA,
)
from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.data.paths import DataPaths
from quintet.tau.lookback_builder import refresh_system_lookback


def wilson_lower_bound(
    k: np.ndarray | float,
    tp: np.ndarray | float,
    alpha: float = WILSON_ALPHA,
) -> np.ndarray | float:
    """Wilson score lower bound for observed precision tp/k.

    Vectorized over k.
    """
    p_hat = tp / k
    z = norm.ppf(1 - alpha / 2)
    denom = 1 + z**2 / k
    center = (p_hat + z**2 / (2 * k)) / denom
    margin = (z / denom) * np.sqrt(p_hat * (1 - p_hat) / k + z**2 / (4 * k**2))
    return center - margin


def calculate_threshold(
    probs: np.ndarray,
    labels: np.ndarray,
    target_precision: float,
    alpha: float = WILSON_ALPHA,
    top_k: int = 50,
) -> tuple[float, dict]:
    """Find the deepest-k probability threshold whose Wilson LB meets target.

    Returns `(tau, diagnostics)`. `tau = NaN` if no k satisfies the bound.
    """
    nan_diag = {
        "n": 0,
        "n_positives": 0,
        "best_k": 0,
        "tp_at_k": 0,
        "precision_at_k": float("nan"),
        "wilson_lb_at_k": float("nan"),
        "best_lb_seen": float("nan"),
        "best_lb_k": 0,
        "top_k_n": 0,
        "top_k_tp": 0,
        "top_k_precision": float("nan"),
    }

    n = len(probs)
    if n == 0:
        return float("nan"), nan_diag

    sorted_indices = np.argsort(probs)[::-1]
    y_sorted = np.asarray(labels)[sorted_indices]

    tp_cumsum = np.cumsum(y_sorted)
    k = np.arange(1, n + 1, dtype=float)

    lower_bounds = wilson_lower_bound(k, tp_cumsum, alpha=alpha)

    n_positives = int(tp_cumsum[-1])
    best_lb_idx = int(np.argmax(lower_bounds))
    best_lb_seen = float(lower_bounds[best_lb_idx])
    best_lb_k = best_lb_idx + 1

    top_k_eff = min(top_k, n)
    top_k_tp = int(tp_cumsum[top_k_eff - 1])
    top_k_precision = float(top_k_tp / top_k_eff)

    common = {
        "n": n,
        "n_positives": n_positives,
        "best_lb_seen": best_lb_seen,
        "best_lb_k": best_lb_k,
        "top_k_n": top_k_eff,
        "top_k_tp": top_k_tp,
        "top_k_precision": top_k_precision,
    }

    valid = np.where(lower_bounds >= target_precision)[0]
    if len(valid) == 0:
        return float("nan"), {
            **common,
            "best_k": 0,
            "tp_at_k": 0,
            "precision_at_k": float("nan"),
            "wilson_lb_at_k": float("nan"),
        }

    best_k = int(valid[-1] + 1)
    tau = float(probs[sorted_indices[best_k - 1]])
    tp_at_k = int(tp_cumsum[best_k - 1])
    precision_at_k = float(tp_at_k / best_k)
    return tau, {
        **common,
        "best_k": best_k,
        "tp_at_k": tp_at_k,
        "precision_at_k": precision_at_k,
        "wilson_lb_at_k": float(lower_bounds[best_k - 1]),
    }


def _save_tau_json(paths: DataPaths, system: str, result: dict) -> None:
    """Persist the per-system tau snapshot to processed/{system}/_tau.json."""
    out = {
        k: (None if isinstance(v, float) and math.isnan(v) else v)
        for k, v in result.items()
    }
    with open(paths.tau_json_path(system), "w") as f:
        json.dump(out, f, indent=2)


def compute_system_tau(
    system: str,
    today: date,
    registry: ContractRegistry,
    paths: DataPaths,
    target_bars: int = LOOKBACK_WINDOW,
) -> dict:
    """Compute today's tau for `system`.

    Refreshes per-product `_lookback/{product}.parquet` files (rebuilding
    only the products whose newest expired contract has changed since
    last run), pools every product's lookback into one array, runs the
    Wilson walkdown, and writes `processed/{system}/_tau.json` with the
    snapshot.

    Returns a dict with `tau`, pool size, positive count, gate_pass, the
    diagnostic fields from `calculate_threshold`, the contributing
    `products`, and a `lookback_status` summary
    (`{cached: int, rebuilt: int, no_eligible: int}`).
    """
    label = SYSTEM_LABEL[system]
    label_col = f"Label_{label}"

    lookbacks, status_counts = refresh_system_lookback(
        system, today, registry, paths, target_bars
    )

    base = {
        "system": system,
        "today": str(today),
        "target": PRECISION[system],
        "lookback_status": status_counts,
    }

    if not lookbacks:
        result = {
            **base,
            "tau": float("nan"),
            "n_pool": 0,
            "n_positives": 0,
            "gate_pass": False,
            "best_k": 0,
            "tp_at_k": 0,
            "precision_at_k": float("nan"),
            "wilson_lb_at_k": float("nan"),
            "best_lb_seen": float("nan"),
            "best_lb_k": 0,
            "top_k_n": 0,
            "top_k_tp": 0,
            "top_k_precision": float("nan"),
            "products": [],
        }
        _save_tau_json(paths, system, result)
        return result

    arrays = []
    for df in lookbacks.values():
        arrays.append(np.column_stack([df["prob"].values, df[label_col].values]))
    pool = np.vstack(arrays)

    tau, diag = calculate_threshold(
        pool[:, 0], pool[:, 1], PRECISION[system], WILSON_ALPHA,
    )

    result = {
        **base,
        "tau": tau,
        "n_pool": diag["n"],
        "n_positives": diag["n_positives"],
        "gate_pass": not (isinstance(tau, float) and np.isnan(tau)),
        "best_k": diag["best_k"],
        "tp_at_k": diag["tp_at_k"],
        "precision_at_k": diag["precision_at_k"],
        "wilson_lb_at_k": diag["wilson_lb_at_k"],
        "best_lb_seen": diag["best_lb_seen"],
        "best_lb_k": diag["best_lb_k"],
        "top_k_n": diag["top_k_n"],
        "top_k_tp": diag["top_k_tp"],
        "top_k_precision": diag["top_k_precision"],
        "products": list(lookbacks.keys()),
    }
    _save_tau_json(paths, system, result)
    return result
