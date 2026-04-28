"""Tau page - per-system Wilson-LB threshold summary + 60-bar lookback charts."""

from __future__ import annotations

import dash
from dash import Input, Output, callback, dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from quintet.config import PRECISION, SYSTEM_LABEL, SYSTEM_SIDE, SYSTEMS
from quintet.dashboard.components.charts.lookback_chart import create_lookback_figure
from quintet.dashboard.config import CHART_CONFIG, PRODUCT_GROUPS
from quintet.dashboard.data.loader import (
    compute_product_precision,
    get_product_info,
    list_lookback_products,
    load_lookback,
    load_tau_snapshot,
)

dash.register_page(__name__, path="/tau", name="Tau", order=1)

ALL_SYSTEMS_VALUE = "_all"
ALL_GROUPS_VALUE = "_all"


# =============================================================================
# Layout + controls
# =============================================================================

def _system_dropdown() -> dbc.Col:
    options = [{"label": "All", "value": ALL_SYSTEMS_VALUE}]
    options.extend({"label": s, "value": s} for s in SYSTEMS)
    return dbc.Col(
        [
            dbc.Label("System", html_for="tau-system-dropdown"),
            dbc.Select(
                id="tau-system-dropdown",
                options=options,
                value=ALL_SYSTEMS_VALUE,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=3,
    )


def _group_dropdown() -> dbc.Col:
    options = [{"label": "All", "value": ALL_GROUPS_VALUE}]
    options.extend({"label": name, "value": name} for name, _ in PRODUCT_GROUPS)
    return dbc.Col(
        [
            dbc.Label("Group", html_for="tau-group-dropdown"),
            dbc.Select(
                id="tau-group-dropdown",
                options=options,
                value=ALL_GROUPS_VALUE,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=3,
    )


def _view_dropdown() -> dbc.Col:
    options = [
        {"label": "Summary", "value": "summary"},
        {"label": "Lookback", "value": "lookback"},
    ]
    return dbc.Col(
        [
            dbc.Label("View", html_for="tau-view-dropdown"),
            dbc.Select(
                id="tau-view-dropdown",
                options=options,
                value="summary",
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=3,
    )


def layout() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row(
                [_view_dropdown(), _system_dropdown(), _group_dropdown()],
                className="mb-4",
            ),
            dbc.Spinner(html.Div(id="tau-content"), color="primary"),
        ],
        fluid=True,
        className="mt-4",
    )


# =============================================================================
# Visibility callbacks
# =============================================================================

@callback(
    Output("tau-group-dropdown", "disabled"),
    Input("tau-view-dropdown", "value"),
)
def toggle_group_dropdown(view: str | None):
    return view != "lookback"


# =============================================================================
# Main render callback
# =============================================================================

@callback(
    Output("tau-content", "children"),
    Input("tau-view-dropdown", "value"),
    Input("tau-system-dropdown", "value"),
    Input("tau-group-dropdown", "value"),
)
def render(view: str | None, system: str | None, group: str | None):
    systems = _resolve_systems(system)
    if not systems:
        return _info("No systems selected.")

    if view == "lookback":
        return _render_lookback(systems, group or ALL_GROUPS_VALUE)
    return _render_summary(systems)


def _resolve_systems(system: str | None) -> list[str]:
    if not system or system == ALL_SYSTEMS_VALUE:
        return list(SYSTEMS)
    if system in SYSTEMS:
        return [system]
    return []


def _info(text: str) -> html.Div:
    return html.Div(text, className="text-muted text-center mt-5")


# =============================================================================
# Summary view
# =============================================================================

def _render_summary(systems: list[str]) -> list:
    cards = []
    for sys in systems:
        cards.append(_summary_card(sys))
    return cards


def _summary_card(system: str) -> dbc.Card:
    snap = load_tau_snapshot(system)
    label = SYSTEM_LABEL[system]
    side = SYSTEM_SIDE[system]
    target = PRECISION[system]

    products = list_lookback_products(system)
    per_product = []
    for p in products:
        m = compute_product_precision(system, p)
        if m is not None:
            per_product.append(m)
    per_product.sort(key=lambda m: (m["best_k"], m["n_tp"]), reverse=True)
    n_hit = sum(1 for m in per_product if m["hit"])

    header = html.Div(
        [
            html.Span(
                f"{system}",
                style={"fontWeight": 600, "fontSize": "1.05rem"},
            ),
            html.Span(
                f"  ·  label {label}  ·  {side}  ·  target {target:.2%}",
                style={"color": "#888", "marginLeft": "8px"},
            ),
        ]
    )

    if not snap:
        body = _info(f"No _tau.json for {system}.")
    else:
        body = html.Div(
            [
                _system_stats_table(snap, n_hit, len(per_product)),
                html.Hr(style={"borderColor": "#333"}),
                _per_product_table(per_product),
            ]
        )

    return dbc.Card(
        [dbc.CardHeader(header), dbc.CardBody(body)],
        className="mb-4",
    )


def _fmt(v, spec: str = ".4f") -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and v != v:  # NaN
        return "—"
    return format(v, spec)


def _system_stats_table(snap: dict, n_hit: int, n_total: int) -> html.Table:
    tau = snap.get("tau")
    gate = snap.get("gate_pass", False)
    badge_color = "#2A9D8F" if gate else "#E63946"
    rows = [
        ("Today", snap.get("today", "—")),
        ("Tau", _fmt(tau)),
        (
            "Gate",
            html.Span(
                "PASS" if gate else "FAIL",
                style={"color": badge_color, "fontWeight": 600},
            ),
        ),
        ("Best k", _fmt(snap.get("best_k"), "d") if snap.get("best_k") else "—"),
        ("Precision @ k", _fmt(snap.get("precision_at_k"), ".2%")),
        ("Wilson LB @ k", _fmt(snap.get("wilson_lb_at_k"), ".4f")),
        ("Pool size", _fmt(snap.get("n_pool"), ",d")),
        ("Positives", _fmt(snap.get("n_positives"), ",d")),
        ("Products hit", f"{n_hit} / {n_total}"),
    ]
    body = []
    for label, value in rows:
        body.append(
            html.Tr(
                [
                    html.Td(label, style={"color": "#888", "width": "180px"}),
                    html.Td(value),
                ]
            )
        )
    return html.Table(html.Tbody(body), className="table table-sm table-dark mb-0")


def _per_product_table(rows: list[dict]) -> html.Table:
    if not rows:
        return _info("No products with lookback data.")

    head = html.Thead(
        html.Tr(
            [
                html.Th("Product"),
                html.Th("Name"),
                html.Th("k"),
                html.Th("TP"),
                html.Th("Prec@k"),
                html.Th("Wilson LB"),
                html.Th("Tau"),
                html.Th("PosRate"),
                html.Th("Hit"),
            ]
        )
    )

    body_rows = []
    for r in rows:
        info = get_product_info(r["product"])
        long_name = info.get("longName", r["product"])
        hit_color = "#2A9D8F" if r["hit"] else "#888"
        body_rows.append(
            html.Tr(
                [
                    html.Td(r["product"]),
                    html.Td(long_name, style={"color": "#aaa"}),
                    html.Td(_fmt(r["best_k"], "d") if r["best_k"] else "—"),
                    html.Td(_fmt(r["n_tp"], "d") if r["n_tp"] else "—"),
                    html.Td(_fmt(r["precision_at_k"], ".2%")),
                    html.Td(_fmt(r["wilson_lb_at_k"], ".4f")),
                    html.Td(_fmt(r["tau"], ".4f")),
                    html.Td(_fmt(r["pos_rate"], ".2%")),
                    html.Td(
                        html.Span(
                            "✓" if r["hit"] else "·",
                            style={"color": hit_color, "fontWeight": 600},
                        )
                    ),
                ]
            )
        )

    return html.Table(
        [head, html.Tbody(body_rows)],
        className="table table-sm table-dark mb-0",
    )


# =============================================================================
# Lookback view
# =============================================================================

def _render_lookback(systems: list[str], group: str) -> list:
    blocks: list = []
    group_to_symbols = dict(PRODUCT_GROUPS)

    for sys in systems:
        snap = load_tau_snapshot(sys)
        tau = snap.get("tau") if snap else None
        available = set(list_lookback_products(sys))
        if not available:
            continue

        blocks.append(_system_header(sys, tau))

        for group_name, symbols in PRODUCT_GROUPS:
            if group != ALL_GROUPS_VALUE and group != group_name:
                continue
            members = [s for s in symbols if s in available]
            if not members:
                continue
            blocks.append(_group_header(group_name))
            for symbol in members:
                blocks.append(_lookback_chart_block(sys, symbol, tau))

    if not blocks:
        return [_info("No lookback data for the current selection.")]
    return blocks


def _system_header(system: str, tau: float | None) -> html.Div:
    label = SYSTEM_LABEL[system]
    side = SYSTEM_SIDE[system]
    target = PRECISION[system]
    tau_str = f"τ {tau:.4f}" if tau is not None else "τ —"
    return html.Div(
        [
            html.H4(
                f"{system}",
                style={"display": "inline-block", "color": "#fff", "marginRight": "12px"},
            ),
            html.Span(
                f"label {label} · {side} · target {target:.2%} · {tau_str}",
                style={"color": "#888", "fontSize": "0.95rem"},
            ),
        ],
        style={
            "borderBottom": "2px solid #555",
            "paddingBottom": "6px",
            "marginTop": "24px",
            "marginBottom": "12px",
        },
    )


def _group_header(group_name: str) -> html.H5:
    return html.H5(
        group_name,
        className="mt-3 mb-2",
        style={
            "color": "#888",
            "borderBottom": "1px solid #333",
            "paddingBottom": "4px",
        },
    )


def _lookback_chart_block(system: str, product: str, tau: float | None) -> html.Div:
    try:
        df = load_lookback(system, product)
    except FileNotFoundError as e:
        return _error_block(f"{system}/{product}: {e}")

    info = get_product_info(product)
    long_name = info.get("longName", product)

    metrics = compute_product_precision(system, product)
    subtitle_parts = [f"{system}"]
    if metrics and metrics["best_k"]:
        subtitle_parts.append(
            f"k={metrics['best_k']} · prec@k={metrics['precision_at_k']:.1%} · "
            f"WilsonLB={metrics['wilson_lb_at_k']:.4f} · τ={metrics['tau']:.4f}"
        )
    elif metrics:
        subtitle_parts.append(f"no per-product k (pos_rate={metrics['pos_rate']:.1%})")
    subtitle = " · ".join(subtitle_parts)

    try:
        fig = create_lookback_figure(df=df, system=system, tau=tau)
    except Exception as e:
        return _error_block(f"{system}/{product}: {e}")

    return html.Div(
        [
            html.H5(
                f"{long_name} ({product})",
                style={
                    "color": "#ccc",
                    "textAlign": "center",
                    "marginBottom": "4px",
                    "fontWeight": 500,
                },
            ),
            html.P(
                subtitle,
                style={
                    "color": "#888",
                    "textAlign": "center",
                    "fontSize": "0.85rem",
                    "marginBottom": "6px",
                },
            ),
            dcc.Graph(figure=fig, config=CHART_CONFIG),
        ],
        className="mb-4",
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
    return html.Div([dcc.Graph(figure=fig, config=CHART_CONFIG)], className="mb-4")
