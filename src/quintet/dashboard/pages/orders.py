"""Latest-run broker open orders view."""

from __future__ import annotations

import dash
from dash import Input, Output, callback, html
import dash_bootstrap_components as dbc

from quintet.config import SYSTEMS
from quintet.dashboard.data.loader import (
    load_latest_execution_report,
    load_order_rows,
)

dash.register_page(__name__, path="/orders", name="Orders", order=4)

ALL_VALUE = "_all"

_ROLE_ORDER = [
    "entry_orders",
    "entry_bracket_stops",
    "current_position_stops",
    "old_position_stops",
    "other_orders",
]
_ROLE_LABELS = {
    "entry_orders": "Entry Orders",
    "entry_bracket_stops": "Entry Bracket Stops",
    "current_position_stops": "Current Position Stops",
    "old_position_stops": "Old Position Stops",
    "other_orders": "Other Orders",
}
_STATUS_COLORS = {
    "PendingSubmit": "#6C757D",
    "PreSubmitted": "#0D6EFD",
    "Submitted": "#2A9D8F",
    "Filled": "#6C757D",
    "Cancelled": "#6C757D",
    "Inactive": "#E76F51",
    "Unknown": "#6C757D",
}


def layout() -> dbc.Container:
    rows = load_order_rows()
    return dbc.Container(
        [
            dbc.Row(
                [
                    _select_col("orders-system-dropdown", "System", _system_options()),
                    _select_col("orders-status-dropdown", "Status", _status_options(rows)),
                    _select_col("orders-symbol-dropdown", "Symbol", _symbol_options(rows)),
                ],
                className="mb-4",
            ),
            dbc.Spinner(html.Div(id="orders-content"), color="primary"),
        ],
        fluid=True,
        className="mt-4",
    )


def _select_col(select_id: str, label: str, options: list[dict]) -> dbc.Col:
    return dbc.Col(
        [
            dbc.Label(label, html_for=select_id),
            dbc.Select(
                id=select_id,
                options=options,
                value=ALL_VALUE,
                persistence=True,
                persistence_type="session",
            ),
        ],
        md=3,
    )


def _system_options() -> list[dict]:
    return [{"label": "All", "value": ALL_VALUE}] + [
        {"label": system, "value": system} for system in SYSTEMS
    ]


def _status_options(rows: list[dict]) -> list[dict]:
    statuses = sorted({row.get("status") or "Unknown" for row in rows})
    return [{"label": "All", "value": ALL_VALUE}] + [
        {"label": status, "value": status} for status in statuses
    ]


def _symbol_options(rows: list[dict]) -> list[dict]:
    symbols = sorted({row.get("symbol") for row in rows if row.get("symbol")})
    return [{"label": "All", "value": ALL_VALUE}] + [
        {"label": symbol, "value": symbol} for symbol in symbols
    ]


@callback(
    Output("orders-content", "children"),
    Input("orders-system-dropdown", "value"),
    Input("orders-status-dropdown", "value"),
    Input("orders-symbol-dropdown", "value"),
)
def render(system: str | None, status: str | None, symbol: str | None):
    all_rows = load_order_rows()
    rows = _filter_rows(all_rows, system, status, symbol)
    report = load_latest_execution_report()
    if not rows:
        message = "No matching open orders in the latest execution report snapshot."
        if not all_rows:
            message = "No open orders in the latest execution report snapshot."
        return html.Div(
            message,
            className="text-muted text-center mt-5",
        )

    return [
        _summary_card(rows, report),
        *_order_sections(rows),
    ]


def _filter_rows(
    rows: list[dict],
    system: str | None,
    status: str | None,
    symbol: str | None,
) -> list[dict]:
    if system and system != ALL_VALUE:
        rows = [row for row in rows if row.get("system") == system]
    if status and status != ALL_VALUE:
        rows = [row for row in rows if row.get("status") == status]
    if symbol and symbol != ALL_VALUE:
        rows = [row for row in rows if row.get("symbol") == symbol]
    return rows


def _summary_card(rows: list[dict], report: dict) -> dbc.Card:
    generated = report.get("generated_at") or "-"
    systems = len({row.get("system") for row in rows if row.get("system")})
    statuses = len({row.get("status") for row in rows if row.get("status")})
    role_counts = _count_roles(rows)
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div("Latest broker orders", className="text-muted small"),
                html.H4(f"{len(rows)} open order(s)", className="mb-2"),
                html.Div(
                    [
                        _pill("systems", systems),
                        _pill("statuses", statuses),
                        *[
                            _pill(_ROLE_LABELS[role].lower(), count)
                            for role, count in role_counts.items()
                        ],
                        _pill("snapshot", generated),
                    ],
                    className="d-flex gap-2 flex-wrap",
                ),
            ]
        ),
        className="mb-3",
    )


def _count_roles(rows: list[dict]) -> dict[str, int]:
    counts = {role: 0 for role in _ROLE_ORDER}
    for row in rows:
        role = row.get("role") or "other_orders"
        counts[role] = counts.get(role, 0) + 1
    return {role: counts[role] for role in _ROLE_ORDER if counts.get(role)}


def _order_sections(rows: list[dict]) -> list[dbc.Card]:
    grouped: dict[str, list[dict]] = {role: [] for role in _ROLE_ORDER}
    for row in rows:
        role = row.get("role") or "other_orders"
        grouped.setdefault(role, []).append(row)
    return [
        _orders_table(_ROLE_LABELS.get(role, "Other Orders"), grouped[role])
        for role in _ROLE_ORDER
        if grouped.get(role)
    ]


def _orders_table(title: str, rows: list[dict]) -> dbc.Card:
    table_rows = [
        html.Tr(
            [
                html.Td(_status_badge(row.get("status"))),
                html.Td(row.get("order_id") or "-"),
                html.Td(row.get("system") or "-"),
                html.Td(row.get("symbol") or "-"),
                html.Td(row.get("local_symbol") or "-"),
                html.Td(row.get("action") or "-"),
                html.Td(row.get("order_type") or "-"),
                html.Td(_fmt_qty(row.get("quantity"))),
                html.Td(_fmt_float(row.get("aux_price"))),
                html.Td(_fmt_float(row.get("limit_price"))),
                html.Td(row.get("parent_id") or "-"),
                html.Td(row.get("oca_group") or "-"),
                html.Td(row.get("order_ref") or "-"),
                html.Td(row.get("tif") or "-"),
                html.Td(_fmt_bool(row.get("transmit"))),
            ]
        )
        for row in rows
    ]
    return dbc.Card(
        [
            dbc.CardHeader(title),
            dbc.CardBody(
                dbc.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Status"),
                                    html.Th("Order ID"),
                                    html.Th("System"),
                                    html.Th("Symbol"),
                                    html.Th("Contract"),
                                    html.Th("Action"),
                                    html.Th("Type"),
                                    html.Th("Qty"),
                                    html.Th("Stop/Aux"),
                                    html.Th("Limit"),
                                    html.Th("Parent"),
                                    html.Th("OCA"),
                                    html.Th("Ref"),
                                    html.Th("TIF"),
                                    html.Th("Transmit"),
                                ]
                            )
                        ),
                        html.Tbody(table_rows),
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


def _pill(label: str, value) -> html.Span:
    return html.Span(
        f"{label}: {value}",
        className="badge rounded-pill bg-secondary",
        style={"fontSize": "0.78rem"},
    )


def _status_badge(status: str | None) -> html.Span:
    text = status or "Unknown"
    return html.Span(
        text,
        style={
            "backgroundColor": _STATUS_COLORS.get(text, "#6C757D"),
            "color": "#fff",
            "padding": "2px 8px",
            "borderRadius": "10px",
            "fontSize": "0.72rem",
            "fontWeight": 700,
            "whiteSpace": "nowrap",
        },
    )


def _fmt_float(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.4f}"
    except (TypeError, ValueError):
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


def _fmt_bool(value) -> str:
    if value is None:
        return "-"
    return "yes" if bool(value) else "no"
