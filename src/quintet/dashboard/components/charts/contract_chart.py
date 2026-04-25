"""Contract chart component - OHLC with S/R overlays and probability subplot."""

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from quintet.config import INDICATORS, SYSTEMS
from quintet.dashboard.config import (
    CHART_HEIGHT,
    LAST_DAY_COLOR,
    OHLC_DECREASING,
    OHLC_INCREASING,
    PROB_COLORS,
    RESISTANCE_COLOR,
    SCAN_END_COLOR,
    SCAN_START_COLOR,
    SUBPLOT_ROW_HEIGHTS,
    SUPPORT_COLOR,
)
from quintet.dashboard.data.loader import ContractDates


def create_contract_figure(
    df: pd.DataFrame | None,
    title: str = "",
    days: int = 90,
    contract_dates: ContractDates | None = None,
    system_filter: str = "all",
) -> go.Figure:
    """OHLC + Sup/Res overlays with a probability subplot.

    Args:
        df: Merged contract frame (Open/High/Low/Settle/Volume, Sup_w/Res_w
            for windows present, prob_{C4,CS4,E4,E7,E13} for systems present).
        title: Chart title.
        days: Number of trailing days to show (0 for all).
        contract_dates: Optional scan_start / scan_end / last_day markers.
        system_filter: "all" or one of C4/CS4/E4/E7/E13.
    """
    if df is None or len(df) == 0:
        return _create_empty_figure(title)

    if days > 0:
        cutoff = df.index.max() - timedelta(days=days)
        df = df[df.index >= cutoff]

    if len(df) == 0:
        return _create_empty_figure(title)

    exclude_dates = _calc_exclude_dates(df)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=SUBPLOT_ROW_HEIGHTS,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )

    _add_all_sr_traces(fig, df, system_filter)
    _add_volume_bars(fig, df)
    _add_ohlc_trace(fig, df)
    _add_probability_traces(fig, df, system_filter)

    if contract_dates:
        _add_date_lines(fig, contract_dates, df)

    _configure_layout(fig, exclude_dates, df)
    return fig


def _add_all_sr_traces(fig: go.Figure, df: pd.DataFrame, system_filter: str = "all") -> None:
    if system_filter == "all":
        pairs = sorted({(INDICATORS[s][0], INDICATORS[s][1]) for s in SYSTEMS})
    elif system_filter in INDICATORS:
        pairs = [(INDICATORS[system_filter][0], INDICATORS[system_filter][1])]
    else:
        pairs = []

    for sup_col, res_col in pairs:
        window = sup_col.split("_", 1)[1]

        if sup_col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[sup_col],
                    name=f"Sup {window}",
                    line=dict(color=SUPPORT_COLOR, width=1.5),
                    hovertemplate=f"Sup {window}: %{{y:.2f}}<extra></extra>",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )

        if res_col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[res_col],
                    name=f"Res {window}",
                    line=dict(color=RESISTANCE_COLOR, width=1.5),
                    hovertemplate=f"Res {window}: %{{y:.2f}}<extra></extra>",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )


def _add_ohlc_trace(fig: go.Figure, df: pd.DataFrame) -> None:
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


def _add_volume_bars(fig: go.Figure, df: pd.DataFrame) -> None:
    if "Volume" not in df.columns:
        return

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="Volume",
            marker_color="rgba(128,128,128,0.3)",
            hovertemplate="Vol: %{y:,.0f}<extra></extra>",
            showlegend=False,
        ),
        row=1,
        col=1,
        secondary_y=True,
    )


def _add_probability_traces(fig: go.Figure, df: pd.DataFrame, system_filter: str = "all") -> None:
    for prob_col, color in PROB_COLORS.items():
        if system_filter != "all" and not prob_col.endswith(f"_{system_filter}"):
            continue
        if prob_col not in df.columns:
            continue

        label = prob_col.replace("prob_", "")
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[prob_col],
                name=label,
                line=dict(color=color, width=1.5),
                hovertemplate=f"{label}: %{{y:.3f}}<extra></extra>",
            ),
            row=2,
            col=1,
        )


def _add_date_lines(
    fig: go.Figure,
    contract_dates: ContractDates,
    df: pd.DataFrame,
) -> None:
    date_configs = [
        (contract_dates.start_scan, SCAN_START_COLOR, "Scan Start"),
        (contract_dates.end_scan, SCAN_END_COLOR, "Scan End"),
        (contract_dates.last_day, LAST_DAY_COLOR, "Last Day"),
    ]

    min_date = df.index.min()
    max_date = df.index.max()

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
    min_date = df.index.min()
    max_date = df.index.max()
    all_dates = pd.date_range(min_date, max_date, freq="D")
    trading_dates = {d.date() for d in df.index}
    return [d for d in all_dates if d.date() not in trading_dates]


def _configure_layout(fig: go.Figure, exclude_dates: list, df: pd.DataFrame) -> None:
    fig.update_layout(
        height=CHART_HEIGHT,
        xaxis_rangeslider_visible=False,
        xaxis_showgrid=False,
        showlegend=False,
        margin=dict(l=50, r=50, t=30, b=50),
        hovermode="x unified",
    )

    if exclude_dates:
        fig.update_xaxes(rangebreaks=[dict(values=exclude_dates)])

    fig.update_yaxes(title_text="", row=1, col=1)
    fig.update_yaxes(title_text="", row=2, col=1)

    if "Volume" in df.columns:
        max_vol = df["Volume"].max()
        if max_vol > 0:
            fig.update_yaxes(
                range=[0, max_vol * 6],
                visible=False,
                secondary_y=True,
                row=1,
                col=1,
            )

    fig.update_xaxes(domain=[0, 1])
    fig.update_xaxes(title_text="", row=2, col=1)


def _create_empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text="No data available",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=20),
    )
    fig.update_layout(title=title, height=CHART_HEIGHT)
    return fig
