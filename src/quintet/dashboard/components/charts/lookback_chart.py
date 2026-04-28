"""Lookback chart - 60-bar OHLC + prob/tau subplot for the Tau page.

The lookback parquet schema is `timestamp, contract, open, high, low,
close, prob, Label_{N}` — no Sup/Res, no volume — so this chart is
deliberately simpler than `contract_chart.py`. Two stacked subplots:

  Top: OHLC. Vertical lines at every contract change (annotated with
       the new local symbol) so contract-roll boundaries are visible.
       Green vlines on Label_N == 1 rows.

  Bottom: prob line. Horizontal dashed line at tau when tau is not
          None (i.e. the system gate passed for the day).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quintet.config import SYSTEM_LABEL
from quintet.dashboard.config import (
    CHART_HEIGHT,
    OHLC_DECREASING,
    OHLC_INCREASING,
    SCAN_START_COLOR,
    SUBPLOT_ROW_HEIGHTS,
)


_LABEL_SUCCESS_COLOR = "rgba(38, 166, 154, 0.5)"
_PROB_COLOR = "#457B9D"
_TAU_COLOR = "#F4A261"


def create_lookback_figure(
    df: pd.DataFrame | None,
    system: str,
    tau: float | None,
) -> go.Figure:
    """Render a 60-bar lookback figure for one (system, product)."""
    if df is None or len(df) == 0:
        return _empty_figure()

    label_col = f"Label_{SYSTEM_LABEL[system]}"

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=SUBPLOT_ROW_HEIGHTS,
    )

    _add_label_success_lines(fig, df, label_col)
    _add_ohlc(fig, df)
    _add_prob_line(fig, df)
    _add_tau_hline(fig, df, tau)
    _add_contract_boundaries(fig, df)

    _configure_layout(fig, df)
    return fig


def _add_ohlc(fig: go.Figure, df: pd.DataFrame) -> None:
    fig.add_trace(
        go.Ohlc(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Settle"],
            increasing_line_color=OHLC_INCREASING,
            decreasing_line_color=OHLC_DECREASING,
            name="",
            showlegend=False,
        ),
        row=1,
        col=1,
    )


def _add_prob_line(fig: go.Figure, df: pd.DataFrame) -> None:
    if "prob" not in df.columns:
        return
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["prob"],
            mode="lines",
            line=dict(color=_PROB_COLOR, width=1.5),
            name="prob",
            hovertemplate="prob: %{y:.4f}<extra></extra>",
            showlegend=False,
        ),
        row=2,
        col=1,
    )


def _add_tau_hline(fig: go.Figure, df: pd.DataFrame, tau: float | None) -> None:
    if tau is None or len(df) == 0:
        return
    x_min, x_max = df.index.min(), df.index.max()
    fig.add_trace(
        go.Scatter(
            x=[x_min, x_max],
            y=[tau, tau],
            mode="lines",
            line=dict(color=_TAU_COLOR, width=1, dash="dash"),
            name=f"τ {tau:.4f}",
            hovertemplate=f"τ: {tau:.4f}<extra></extra>",
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    fig.add_annotation(
        x=x_max,
        y=tau,
        text=f"  τ {tau:.4f}",
        showarrow=False,
        xanchor="left",
        font=dict(size=10, color=_TAU_COLOR),
        row=2,
        col=1,
    )


def _add_label_success_lines(fig: go.Figure, df: pd.DataFrame, label_col: str) -> None:
    if label_col not in df.columns or "Low" not in df.columns:
        return
    mask = df[label_col].notna() & (df[label_col] == 1)
    xs = df.index[mask]
    if len(xs) == 0:
        return

    y_min = df["Low"].min()
    y_max = df["High"].max()
    x_vals: list = []
    y_vals: list = []
    for x in xs:
        x_vals.extend([x, x, None])
        y_vals.extend([y_min, y_max, None])

    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines",
            line=dict(color=_LABEL_SUCCESS_COLOR, width=1),
            opacity=0.45,
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=1,
    )


def _add_contract_boundaries(fig: go.Figure, df: pd.DataFrame) -> None:
    if "contract" not in df.columns:
        return

    contracts = df["contract"]
    prev = None
    for ts in df.index:
        cur = contracts.loc[ts]
        if cur != prev:
            ts_pd = pd.Timestamp(ts)
            fig.add_shape(
                type="line",
                x0=ts_pd,
                x1=ts_pd,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color=SCAN_START_COLOR, width=1.2, dash="dot"),
            )
            fig.add_annotation(
                x=ts_pd,
                y=1,
                yref="paper",
                text=cur,
                showarrow=False,
                font=dict(size=10, color=SCAN_START_COLOR),
                yshift=10,
            )
            prev = cur


def _configure_layout(fig: go.Figure, df: pd.DataFrame) -> None:
    fig.update_layout(
        height=CHART_HEIGHT,
        xaxis_rangeslider_visible=False,
        xaxis_showgrid=False,
        showlegend=False,
        margin=dict(l=50, r=50, t=30, b=40),
        hovermode="x unified",
    )

    fig.update_yaxes(title_text="", row=1, col=1)
    fig.update_yaxes(title_text="prob", row=2, col=1)
    fig.update_xaxes(domain=[0, 1])
    fig.update_xaxes(title_text="", row=2, col=1)


def _empty_figure() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text="No lookback data",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=18),
    )
    fig.update_layout(height=CHART_HEIGHT)
    return fig
