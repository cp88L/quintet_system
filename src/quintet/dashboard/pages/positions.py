"""Latest-run broker positions view."""

from __future__ import annotations

import dash
from dash import Input, Output, callback, dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from quintet.config import SYSTEMS
from quintet.dashboard.components.charts.contract_chart import create_contract_figure
from quintet.dashboard.components.controls.selectors import ALL_GROUPS_VALUE
from quintet.dashboard.config import CHART_CONFIG, PRODUCT_GROUPS
from quintet.dashboard.data.loader import (
    format_chart_title,
    get_contract_dates,
    get_product_info,
    load_contract,
    load_position_rows,
)

dash.register_page(__name__, path="/positions", name="Positions", order=3)

ALL_SYSTEMS_VALUE = "_all"

_STATUS_LABELS = {
    "held": "HELD",
    "missing_stop": "MISSING STOP",
    "unknown_system": "UNKNOWN SYSTEM",
}
_STATUS_COLORS = {
    "held": "#2A9D8F",
    "missing_stop": "#E9C46A",
    "unknown_system": "#E76F51",
}


def layout() -> dbc.Container:
    return dbc.Container(
        [
            dbc.Row([_group_dropdown(), _system_dropdown()], className="mb-4"),
            dbc.Spinner(html.Div(id="positions-content"), color="primary"),
        ],
        fluid=True,
        className="mt-4",
    )


def _group_dropdown() -> dbc.Col:
    options = [{"label": "All", "value": ALL_GROUPS_VALUE}]
    options.extend({"label": name, "value": name} for name, _ in PRODUCT_GROUPS)
    return dbc.Col(
        [
            dbc.Label("Group", html_for="positions-group-dropdown"),
            dbc.Select(
                id="positions-group-dropdown",
                options=options,
                value=ALL_GROUPS_VALUE,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=4,
    )


def _system_dropdown() -> dbc.Col:
    options = [{"label": "All", "value": ALL_SYSTEMS_VALUE}]
    options.extend({"label": system, "value": system} for system in SYSTEMS)
    return dbc.Col(
        [
            dbc.Label("System", html_for="positions-system-dropdown"),
            dbc.Select(
                id="positions-system-dropdown",
                options=options,
                value=ALL_SYSTEMS_VALUE,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=3,
    )


@callback(
    Output("positions-content", "children"),
    Input("positions-group-dropdown", "value"),
    Input("positions-system-dropdown", "value"),
)
def render(group: str | None, system: str | None):
    rows = _filter_rows(load_position_rows(), group, system)
    if not rows:
        return html.Div(
            "No positions in the latest execution report snapshot.",
            className="text-muted text-center mt-5",
        )

    children: list = [_summary_card(rows)]
    warning_rows = [row for row in rows if row["status"] != "held"]
    if warning_rows:
        children.append(_warning_card(warning_rows))

    chart_rows = rows
    grouped = _group_chart_rows(chart_rows)
    for group_name, group_rows in grouped:
        children.append(_group_header(group_name))
        for row in group_rows:
            children.append(_position_chart_block(row))

    if not chart_rows:
        children.append(
            html.Div(
                "No chartable positions found in the latest execution report snapshot.",
                className="text-muted text-center mt-5",
            )
        )
    return children


def _filter_rows(rows: list[dict], group: str | None, system: str | None) -> list[dict]:
    symbol_to_group = _symbol_to_group()
    if group and group != ALL_GROUPS_VALUE:
        rows = [row for row in rows if symbol_to_group.get(row["symbol"]) == group]
    if system and system != ALL_SYSTEMS_VALUE:
        rows = [row for row in rows if row.get("system") == system]
    return rows


def _summary_card(rows: list[dict]) -> dbc.Card:
    body_rows = []
    for row in rows:
        info = get_product_info(row["symbol"])
        long_name = info.get("longName", row["symbol"])
        body_rows.append(
            html.Tr(
                [
                    html.Td(_status_badge(row["status"])),
                    html.Td(long_name),
                    html.Td(row["local_symbol"]),
                    html.Td(row.get("system") or "-"),
                    html.Td(_fmt_qty(row.get("quantity"))),
                    html.Td(_fmt_float(row.get("current_price"))),
                    html.Td(_fmt_float(row.get("entry_price"))),
                    html.Td(_fmt_date(row.get("entry_date"))),
                    html.Td(_fmt_money(row.get("unrealized_pnl"), show_plus=True)),
                    html.Td(_fmt_pct(row.get("return_pct"), show_plus=True)),
                    html.Td(_fmt_risk(row)),
                    html.Td(_fmt_float(row.get("stop_price"))),
                    html.Td(_fmt_date(row.get("estimated_last_day"))),
                    html.Td(_fmt_date(row.get("official_last_day"))),
                    html.Td(row.get("stop_order_id") or "-"),
                ]
            )
        )
    return dbc.Card(
        [
            dbc.CardHeader("Latest Broker Positions"),
            dbc.CardBody(
                dbc.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Status"),
                                    html.Th("Product"),
                                    html.Th("Contract"),
                                    html.Th("System"),
                                    html.Th("Qty"),
                                    html.Th("Current"),
                                    html.Th("Entry"),
                                    html.Th("Entry Date"),
                                    html.Th("Return"),
                                    html.Th("Return %"),
                                    html.Th("Current Risk"),
                                    html.Th("Stop"),
                                    html.Th("Estimated Last Day"),
                                    html.Th("LAST DAY"),
                                    html.Th("Stop Order"),
                                ]
                            )
                        ),
                        html.Tbody(body_rows),
                    ],
                    bordered=False,
                    hover=True,
                    responsive=True,
                    size="sm",
                    className="mb-0",
                )
            ),
        ],
        className="mb-4",
    )


def _warning_card(rows: list[dict]) -> dbc.Card:
    body_rows = [
        html.Tr(
            [
                html.Td(_status_badge(row["status"])),
                html.Td(row["local_symbol"]),
                html.Td(row["symbol"]),
                html.Td(_fmt_qty(row.get("quantity"))),
                html.Td(_warning_action(row["status"])),
            ]
        )
        for row in rows
    ]
    return dbc.Card(
        [
            dbc.CardHeader("Position Review"),
            dbc.CardBody(
                dbc.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Status"),
                                    html.Th("Contract"),
                                    html.Th("Symbol"),
                                    html.Th("Qty"),
                                    html.Th("Operator Action"),
                                ]
                            )
                        ),
                        html.Tbody(body_rows),
                    ],
                    bordered=False,
                    hover=True,
                    responsive=True,
                    size="sm",
                    className="mb-0",
                )
            ),
        ],
        className="mb-4",
    )


def _group_chart_rows(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    symbol_to_group = _symbol_to_group()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        group_name = symbol_to_group.get(row["symbol"], "Other")
        grouped.setdefault(group_name, []).append(row)

    ordered: list[tuple[str, list[dict]]] = []
    for group_name, _ in PRODUCT_GROUPS:
        group_rows = grouped.pop(group_name, None)
        if group_rows:
            ordered.append((group_name, group_rows))
    ordered.extend(sorted(grouped.items()))
    return ordered


def _position_chart_block(row: dict) -> html.Div:
    symbol = row["symbol"]
    contract = row["local_symbol"]
    try:
        df = load_contract(symbol, contract)
        contract_dates = get_contract_dates(symbol, contract)
        title = format_chart_title(symbol, contract)
        fig = create_contract_figure(
            df=df,
            days=180,
            contract_dates=contract_dates,
            system_filter=row.get("system") or "all",
            entry_price=row.get("entry_price"),
            stop_price=row.get("stop_price"),
            entry_date=row.get("entry_date"),
            official_last_day=row.get("official_last_day"),
        )
    except Exception as exc:
        return _error_block(f"Error loading {symbol}/{contract}: {exc}")

    subtitle = (
        f"{_STATUS_LABELS.get(row.get('status'), row.get('status', '').upper())} | "
        f"{row.get('system') or '-'} | {row.get('side') or '-'} | "
        f"qty {_fmt_qty(row.get('quantity'))} | "
        f"current {_fmt_float(row.get('current_price'))} | "
        f"entry {_fmt_float(row.get('entry_price'))} | "
        f"entry date {_fmt_date(row.get('entry_date'))} | "
        f"return {_fmt_money(row.get('unrealized_pnl'), show_plus=True)} "
        f"({_fmt_pct(row.get('return_pct'), show_plus=True)}) | "
        f"risk {_fmt_risk(row)} | "
        f"stop {_fmt_float(row.get('stop_price'))} | "
        f"estimated last day {_fmt_date(row.get('estimated_last_day'))} | "
        f"LAST DAY {_fmt_date(row.get('official_last_day'))}"
    )
    return html.Div(
        [
            html.H5(
                title,
                style={
                    "color": "#ccc",
                    "textAlign": "center",
                    "marginBottom": "5px",
                    "fontWeight": "500",
                },
            ),
            html.P(
                subtitle,
                style={
                    "color": "#888",
                    "textAlign": "center",
                    "fontSize": "0.85rem",
                    "marginBottom": "5px",
                },
            ),
            dcc.Graph(figure=fig, config=CHART_CONFIG),
        ],
        className="mb-4",
    )


def _group_header(group_name: str) -> html.H4:
    return html.H4(
        group_name,
        className="mt-4 mb-3",
        style={
            "color": "#888",
            "borderBottom": "1px solid #444",
            "paddingBottom": "8px",
        },
    )


def _status_badge(status: str) -> html.Span:
    return html.Span(
        _STATUS_LABELS.get(status, status.upper()),
        style={
            "backgroundColor": _STATUS_COLORS.get(status, "#555"),
            "color": "#fff",
            "padding": "2px 8px",
            "borderRadius": "10px",
            "fontSize": "0.72rem",
            "fontWeight": 700,
            "letterSpacing": "0.5px",
            "whiteSpace": "nowrap",
        },
    )


def _warning_action(status: str) -> str:
    if status == "missing_stop":
        return "Verify or place the protective stop manually."
    if status == "unknown_system":
        return "Review system attribution; multiple or ambiguous stops matched."
    return "Review position."


def _symbol_to_group() -> dict[str, str]:
    out = {}
    for group_name, symbols in PRODUCT_GROUPS:
        for symbol in symbols:
            out[symbol] = group_name
    return out


def _fmt_float(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_money(value, *, show_plus: bool = False) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    prefix = ""
    if number < 0:
        prefix = "-"
    elif show_plus and number > 0:
        prefix = "+"
    amount = abs(number)
    if amount.is_integer():
        return f"{prefix}${amount:,.0f}"
    return f"{prefix}${amount:,.2f}"


def _fmt_pct(value, *, show_plus: bool = False) -> str:
    if value is None:
        return "-"
    try:
        number = float(value) * 100
    except (TypeError, ValueError):
        return "-"
    sign = "+" if show_plus and number > 0 else ""
    return f"{sign}{number:.2f}%"


def _fmt_risk(row: dict) -> str:
    risk = row.get("current_risk")
    if risk is not None:
        return _fmt_money(risk)
    status = row.get("status")
    if status == "missing_stop":
        return "No stop"
    if status == "unknown_system":
        return "Ambiguous"
    return "-"


def _fmt_qty(value) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _fmt_date(value) -> str:
    if value is None:
        return "-"
    if hasattr(value, "date"):
        value = value.date()
    return str(value)


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
