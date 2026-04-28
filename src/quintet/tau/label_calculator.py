"""Per-system label calculation for tau calibration.

Operates on a single contract DataFrame with `close`, `high`, `low`,
`timestamp`, and `Sup_{label}` / `Res_{label}` columns (as produced by
the indicator step). Sup/Res are NOT pre-shifted on disk — this module
shifts them forward by 1 internally so that same-row comparisons evaluate
day N's levels against day N+1's prices, then shifts the result back so
labels land on the decision row.

For longs: Buy_B is the price below which an entry would break even,
Label = 1 when high < Buy_B.

For shorts: Sell_A is the price above which a short entry would break
even, Label = 1 when low > Sell_A.
"""

from datetime import date

import numpy as np
import pandas as pd

from quintet.config import TARGET_MARGIN


def _effective_last_day(dates: pd.Series, last_trading_day: date) -> date:
    """Snap last_trading_day to the last actual trading day on or before it."""
    on_or_before = dates[dates <= last_trading_day]
    if len(on_or_before) > 0:
        return on_or_before.iloc[-1]
    return last_trading_day


def _entry_levels_long(
    df: pd.DataFrame, label: int, last_trading_day: date
) -> tuple[pd.Series, pd.Series]:
    """Compute Buy_B and Label for the long side, on a Sup/Res-shifted view.

    `df` is the shifted view (sup/res shifted +1, all other columns unshifted).
    Risk uses `prev_close = close.shift(1)` to mirror data_pipeline's
    `prev_settle - sup`. The Sup/Res rolling-min-of-lows construction ensures
    `prev_close >= sup` so risk_pts is non-negative in the scan window.
    """
    highs = df[['high', 'close']].max(axis=1)
    lows = df[['low', 'close']].min(axis=1)
    sup = df[f'Sup_{label}']
    res = df[f'Res_{label}']
    prev_close = df['close'].shift(1)

    dates = pd.to_datetime(df['timestamp']).dt.date
    eff_last = _effective_last_day(dates, last_trading_day)
    last_mask = dates == eff_last
    after_mask = dates > eff_last

    buy_b = lows.where(lows <= sup).copy()
    if last_mask.any():
        buy_b.loc[last_mask] = lows.loc[last_mask].values[0]
    buy_b.loc[after_mask] = np.nan
    buy_b = buy_b.bfill()

    risk_pts = prev_close - sup
    margin_pts = risk_pts * TARGET_MARGIN
    buy_b = buy_b - margin_pts

    label_series = pd.Series(0.0, index=df.index)
    label_series.loc[highs < buy_b] = 1.0
    return buy_b, label_series


def _entry_levels_short(
    df: pd.DataFrame, label: int, last_trading_day: date
) -> tuple[pd.Series, pd.Series]:
    """Compute Sell_A and Label for the short side, on a Sup/Res-shifted view.

    `df` is the shifted view (sup/res shifted +1, all other columns unshifted).
    Risk uses `prev_close = close.shift(1)` to mirror data_pipeline's
    `res - prev_settle`. The Sup/Res rolling-max-of-highs construction
    ensures `res >= prev_close` so risk_pts is non-negative in the scan window.
    """
    highs = df[['high', 'close']].max(axis=1)
    lows = df[['low', 'close']].min(axis=1)
    sup = df[f'Sup_{label}']
    res = df[f'Res_{label}']
    prev_close = df['close'].shift(1)

    dates = pd.to_datetime(df['timestamp']).dt.date
    eff_last = _effective_last_day(dates, last_trading_day)
    last_mask = dates == eff_last
    after_mask = dates > eff_last

    sell_a = highs.where(highs >= res).copy()
    if last_mask.any():
        sell_a.loc[last_mask] = highs.loc[last_mask].values[0]
    sell_a.loc[after_mask] = np.nan
    sell_a = sell_a.bfill()

    risk_pts = res - prev_close
    margin_pts = risk_pts * TARGET_MARGIN
    sell_a = sell_a + margin_pts

    label_series = pd.Series(0.0, index=df.index)
    label_series.loc[lows > sell_a] = 1.0
    return sell_a, label_series


def add_labels(
    df: pd.DataFrame,
    label: int,
    side: str,
    last_trading_day: date,
) -> pd.DataFrame:
    """Add Buy_B/Sell_A and Label columns for one (label, side) configuration.

    Uses shift-compute-unshift to handle the one-day lookahead: same-row
    comparisons after the shift evaluate day N's levels against day N+1's
    prices; the result is shifted back by 1 so labels land on row N.

    The row at `last_trading_day` ends up with NaN labels — there is no
    next day to trade.
    """
    if side not in ("long", "short"):
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")

    sup_col = f'Sup_{label}'
    res_col = f'Res_{label}'
    if sup_col not in df.columns or res_col not in df.columns:
        raise ValueError(f"missing {sup_col} or {res_col}")

    out = df.copy()

    shifted = out.copy()
    shifted[sup_col] = shifted[sup_col].shift(1)
    shifted[res_col] = shifted[res_col].shift(1)

    if side == "long":
        buy_b, label_series = _entry_levels_long(shifted, label, last_trading_day)
        out[f'Buy_B_{label}'] = buy_b.shift(-1)
    else:
        sell_a, label_series = _entry_levels_short(shifted, label, last_trading_day)
        out[f'Sell_A_{label}'] = sell_a.shift(-1)

    out[f'Label_{label}'] = label_series.shift(-1)
    return out
