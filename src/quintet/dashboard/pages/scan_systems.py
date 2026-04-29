"""Entry Scan page — full price chart per in-scan contract for one system.

Single route `/scan` with a system dropdown at the top defaulting to C4.
Each chart card shows the full OHLC + Sup/Res price chart and a prob
subplot with the dashed system τ hline and a dotted today's-prob hline.
Per-product gate state is rendered as colored badges: τ (prob ≥ tau),
C (cluster pass), B (breakout pass) plus a green "ACTIONABLE" tag when
all three pass. Order: actionable first, then by gates-passed, then prob.
"""

from __future__ import annotations

import dash
from dash import Input, Output, callback, dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from quintet.config import SYSTEMS
from quintet.dashboard.components.charts.scan_chart import create_scan_figure
from quintet.dashboard.config import CHART_CONFIG
from quintet.dashboard.data.loader import (
    format_chart_title,
    get_contract_dates,
    get_funnel_summary,
    get_in_scan_for_system,
    load_contract,
)

dash.register_page(__name__, path="/scan", name="Entry Scan", order=2)

DEFAULT_SYSTEM = "C4"

_PASS_COLOR = "#2A9D8F"
_FAIL_COLOR = "#444"
_FAIL_TEXT = "#777"
_ACTIONABLE_BG = "#1f6f5c"


def _system_dropdown() -> dbc.Col:
    options = [{"label": s, "value": s} for s in SYSTEMS]
    return dbc.Col(
        [
            dbc.Label("System", html_for="scan-system-dropdown"),
            dbc.Select(
                id="scan-system-dropdown",
                options=options,
                value=DEFAULT_SYSTEM,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=3,
    )


def layout() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row([_system_dropdown()], className="mb-3"),
            dbc.Spinner(html.Div(id="scan-content"), color="primary"),
        ],
        fluid=True,
        className="mt-4",
    )


@callback(
    Output("scan-content", "children"),
    Input("scan-system-dropdown", "value"),
)
def render(system: str | None):
    if system not in SYSTEMS:
        system = DEFAULT_SYSTEM

    rows = get_in_scan_for_system(system)
    summary = get_funnel_summary(system)
    tau = summary.get("tau")

    children: list = [_system_header(system, summary)]
    if not rows:
        children.append(
            html.Div(
                f"No in-scan contracts for {system}.",
                className="text-muted text-center mt-5",
            )
        )
        return children

    for r in rows:
        children.append(_chart_card(system, r, tau))
    return children


def _system_header(system: str, summary: dict) -> html.Div:
    today = summary.get("today", "—")
    tau = summary.get("tau")
    n_universe = summary.get("n_universe", 0)
    n_actionable = summary.get("n_actionable", 0)
    n_tau = summary.get("n_tau_pass", 0)
    n_cluster = summary.get("n_cluster_pass", 0)
    n_breakout = summary.get("n_breakout_pass", 0)
    tau_str = f"τ {tau:.4f}" if tau is not None else "τ —"
    gate_pass = n_actionable > 0
    gate_color = _PASS_COLOR if gate_pass else "#E63946"
    gate_text = "GATE PASS" if gate_pass else "GATE FAIL"

    info = html.Div(
        [
            html.H3(
                system,
                style={"display": "inline-block", "color": "#fff", "margin": 0},
            ),
            html.Span(
                f"  ·  {today}  ·  {tau_str}  ·  ",
                style={"color": "#888", "marginLeft": "8px"},
            ),
            html.Span(
                gate_text,
                style={
                    "color": "#fff",
                    "backgroundColor": gate_color,
                    "padding": "3px 10px",
                    "borderRadius": "4px",
                    "fontSize": "0.8rem",
                    "fontWeight": 800,
                    "letterSpacing": "1px",
                    "marginLeft": "4px",
                },
            ),
        ],
        style={"display": "flex", "alignItems": "center"},
    )

    counters = html.Div(
        [
            _counter_chip("TAU", n_tau, n_universe),
            _counter_chip("CLUSTER", n_cluster, n_universe),
            _counter_chip("BREAKOUT", n_breakout, n_universe),
            _counter_chip("ACTIONABLE", n_actionable, n_universe, primary=True),
        ],
        style={"display": "flex", "gap": "8px", "marginLeft": "auto"},
    )

    return html.Div(
        [info, counters],
        style={
            "display": "flex",
            "alignItems": "center",
            "borderBottom": "2px solid #555",
            "paddingBottom": "8px",
            "marginBottom": "16px",
        },
    )


def _counter_chip(label: str, n: int, total: int, primary: bool = False) -> html.Span:
    bg = _ACTIONABLE_BG if primary else "#2d2d2d"
    fg = "#fff" if primary else "#ccc"
    return html.Span(
        f"{label} {n}/{total}",
        style={
            "backgroundColor": bg,
            "color": fg,
            "padding": "4px 10px",
            "borderRadius": "12px",
            "fontSize": "0.8rem",
            "fontWeight": 600,
            "letterSpacing": "0.5px",
        },
    )


def _gate_badge(label: str, passed: bool) -> html.Span:
    bg = _PASS_COLOR if passed else _FAIL_COLOR
    fg = "#fff" if passed else _FAIL_TEXT
    return html.Span(
        label,
        style={
            "backgroundColor": bg,
            "color": fg,
            "padding": "2px 10px",
            "borderRadius": "10px",
            "fontSize": "0.72rem",
            "fontWeight": 700,
            "letterSpacing": "0.5px",
            "marginRight": "6px",
            "display": "inline-block",
            "textAlign": "center",
        },
    )


def _actionable_tag() -> html.Span:
    return html.Span(
        "ACTIONABLE",
        style={
            "backgroundColor": _ACTIONABLE_BG,
            "color": "#fff",
            "padding": "3px 10px",
            "borderRadius": "4px",
            "fontSize": "0.75rem",
            "fontWeight": 800,
            "letterSpacing": "1px",
            "marginRight": "10px",
        },
    )


def _chart_card(system: str, row: dict, tau: float | None) -> html.Div:
    symbol = row["symbol"]
    contract = row["contract"]
    prob_today = row["prob"]

    try:
        df = load_contract(symbol, contract)
        contract_dates = get_contract_dates(symbol, contract)
        title = format_chart_title(symbol, contract)
        fig = create_scan_figure(
            df=df,
            system=system,
            contract_dates=contract_dates,
            tau=tau,
            prob_today=prob_today,
        )
    except Exception as e:
        return _error_block(f"Error loading {symbol}/{contract}: {e}")

    cluster_label = "CLUSTER"
    if row.get("cluster_id") is not None:
        cluster_label = f"CLUSTER {row['cluster_id']}"
    badges = [
        _gate_badge("TAU", row["tau_pass"]),
        _gate_badge(cluster_label, row["cluster_pass"]),
        _gate_badge("BREAKOUT", row["breakout_pass"]),
    ]
    title_row = [
        _actionable_tag() if row["actionable"] else None,
        html.Span(
            title,
            style={"color": "#ccc", "fontWeight": 500, "fontSize": "1.1rem"},
        ),
        html.Div(badges, style={"marginLeft": "auto"}),
    ]
    title_row = [el for el in title_row if el is not None]

    border = (
        f"1px solid {_ACTIONABLE_BG}" if row["actionable"] else "1px solid transparent"
    )

    return html.Div(
        [
            html.Div(
                title_row,
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "8px 12px",
                    "backgroundColor": "#222",
                    "borderRadius": "6px 6px 0 0",
                },
            ),
            dcc.Graph(figure=fig, config=CHART_CONFIG),
        ],
        className="mb-4",
        style={"border": border, "borderRadius": "8px", "overflow": "hidden"},
    )


def _error_block(text: str) -> html.Div:
    fig = go.Figure()
    fig.add_annotation(
        text=text,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color="red"),
    )
    fig.update_layout(height=200)
    return html.Div(
        [dcc.Graph(figure=fig, config=CHART_CONFIG)],
        className="mb-4",
    )
