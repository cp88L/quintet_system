"""Scan chart - full price chart with prob/τ subplot for a per-system page.

Row 1: OHLC + system-window Sup/Res + volume overlay (secondary y).
Row 2: prob_{system} line, dashed τ hline, dotted today's-prob hline.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quintet.config import INDICATORS
from quintet.dashboard.config import (
    CHART_HEIGHT,
    LAST_DAY_COLOR,
    OHLC_DECREASING,
    OHLC_INCREASING,
    RESISTANCE_COLOR,
    SCAN_END_COLOR,
    SCAN_START_COLOR,
    SUPPORT_COLOR,
)
from quintet.dashboard.data.loader import ContractDates


_PROB_COLOR = "#457B9D"
_TAU_COLOR = "#F4A261"
_PROB_TODAY_COLOR = "#2A9D8F"


def create_scan_figure(
    df: pd.DataFrame | None,
    system: str,
    contract_dates: ContractDates | None = None,
    tau: float | None = None,
    prob_today: float | None = None,
) -> go.Figure:
    if df is None or len(df) == 0:
        return _empty_figure()

    exclude_dates = _calc_exclude_dates(df)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )

    _add_sr_traces(fig, df, system)
    _add_volume_overlay(fig, df)
    _add_ohlc(fig, df)
    _add_prob_line(fig, df, system)
    _add_tau_hline(fig, df, tau)
    _add_prob_today_hline(fig, df, prob_today)

    if contract_dates:
        _add_date_lines(fig, contract_dates, df)

    _configure_layout(fig, exclude_dates, df)
    return fig


def _add_sr_traces(fig: go.Figure, df: pd.DataFrame, system: str) -> None:
    sup_col = INDICATORS[system][0]
    res_col = INDICATORS[system][1]
    if sup_col in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[sup_col],
                line=dict(color=SUPPORT_COLOR, width=1.5),
                hovertemplate=f"{sup_col}: %{{y:.2f}}<extra></extra>",
                showlegend=False,
                name=sup_col,
            ),
            row=1,
            col=1,
        )
    if res_col in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[res_col],
                line=dict(color=RESISTANCE_COLOR, width=1.5),
                hovertemplate=f"{res_col}: %{{y:.2f}}<extra></extra>",
                showlegend=False,
                name=res_col,
            ),
            row=1,
            col=1,
        )


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


def _add_volume_overlay(fig: go.Figure, df: pd.DataFrame) -> None:
    if "Volume" not in df.columns:
        return
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            marker_color="rgba(128,128,128,0.3)",
            hovertemplate="Vol: %{y:,.0f}<extra></extra>",
            showlegend=False,
            name="Volume",
        ),
        row=1,
        col=1,
        secondary_y=True,
    )


def _add_prob_line(fig: go.Figure, df: pd.DataFrame, system: str) -> None:
    col = f"prob_{system}"
    if col not in df.columns:
        return
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df[col],
            mode="lines",
            line=dict(color=_PROB_COLOR, width=1.5),
            hovertemplate="prob: %{y:.4f}<extra></extra>",
            showlegend=False,
            name="prob",
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
            hovertemplate=f"τ: {tau:.4f}<extra></extra>",
            showlegend=False,
            name="τ",
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


def _add_prob_today_hline(
    fig: go.Figure, df: pd.DataFrame, prob_today: float | None
) -> None:
    if prob_today is None or len(df) == 0:
        return
    x_min, x_max = df.index.min(), df.index.max()
    fig.add_trace(
        go.Scatter(
            x=[x_min, x_max],
            y=[prob_today, prob_today],
            mode="lines",
            line=dict(color=_PROB_TODAY_COLOR, width=1, dash="dot"),
            hovertemplate=f"today: {prob_today:.4f}<extra></extra>",
            showlegend=False,
            name="today",
        ),
        row=2,
        col=1,
    )
    fig.add_annotation(
        x=x_max,
        y=prob_today,
        text=f"  {prob_today:.4f}",
        showarrow=False,
        xanchor="left",
        font=dict(size=10, color=_PROB_TODAY_COLOR),
        row=2,
        col=1,
    )


def _add_date_lines(
    fig: go.Figure, contract_dates: ContractDates, df: pd.DataFrame
) -> None:
    date_configs = [
        (contract_dates.start_scan, SCAN_START_COLOR, "Scan Start"),
        (contract_dates.end_scan, SCAN_END_COLOR, "Scan End"),
        (contract_dates.last_day, LAST_DAY_COLOR, "Last Day"),
    ]
    min_date, max_date = df.index.min(), df.index.max()
    for date_val, color, label in date_configs:
        if date_val is None:
            continue
        date_ts = pd.Timestamp(date_val)
        if date_ts < min_date or date_ts > max_date:
            continue
        fig.add_shape(
            type="line",
            x0=date_ts,
            x1=date_ts,
            y0=0,
            y1=1,
            yref="paper",
            line=dict(color=color, width=1.5, dash="dot"),
        )
        fig.add_annotation(
            x=date_ts,
            y=1,
            yref="paper",
            text=label,
            showarrow=False,
            font=dict(size=10, color=color),
            yshift=10,
        )


def _calc_exclude_dates(df: pd.DataFrame) -> list:
    if len(df) < 2:
        return []
    min_date, max_date = df.index.min(), df.index.max()
    all_dates = pd.date_range(min_date, max_date, freq="D")
    trading_dates = {d.date() for d in df.index}
    return [d for d in all_dates if d.date() not in trading_dates]


def _configure_layout(
    fig: go.Figure, exclude_dates: list, df: pd.DataFrame
) -> None:
    fig.update_layout(
        height=CHART_HEIGHT,
        xaxis_rangeslider_visible=False,
        xaxis_showgrid=False,
        showlegend=False,
        margin=dict(l=50, r=50, t=30, b=40),
        hovermode="x unified",
    )
    if exclude_dates:
        fig.update_xaxes(rangebreaks=[dict(values=exclude_dates)])
    fig.update_yaxes(title_text="", row=1, col=1)
    fig.update_yaxes(title_text="prob", row=2, col=1)
    if "Volume" in df.columns:
        max_vol = df["Volume"].max()
        if max_vol and max_vol > 0:
            fig.update_yaxes(
                range=[0, max_vol * 6],
                visible=False,
                secondary_y=True,
                row=1,
                col=1,
            )
    fig.update_xaxes(domain=[0, 1])
    fig.update_xaxes(title_text="", row=2, col=1)


def _empty_figure() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text="No data available",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=18),
    )
    fig.update_layout(height=CHART_HEIGHT)
    return fig
