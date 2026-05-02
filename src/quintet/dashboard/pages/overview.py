"""Operator overview for the latest broker snapshot and trade run."""

from __future__ import annotations

import dash
from dash import html
import dash_bootstrap_components as dbc

from quintet.dashboard.data.loader import (
    load_latest_broker_state,
    load_latest_execution_report,
    load_latest_trade_plan,
    load_order_rows,
    load_position_rows,
)

dash.register_page(__name__, path="/", name="Overview", order=-1)

_ORDER_ROLE_LABELS = {
    "entry_orders": "Entry Orders",
    "entry_bracket_stops": "Entry Bracket Stops",
    "current_position_stops": "Current Position Stops",
    "old_position_stops": "Old Position Stops",
    "other_orders": "Other Orders",
}
_POSITION_STATUS_LABELS = {
    "held": "HELD",
    "missing_stop": "MISSING STOP",
    "unknown_system": "UNKNOWN SYSTEM",
}


def layout() -> dbc.Container:
    plan = load_latest_trade_plan()
    report = load_latest_execution_report()
    broker_state = load_latest_broker_state()
    positions = load_position_rows()
    orders = load_order_rows()

    if not any([plan, report, broker_state, positions, orders]):
        return dbc.Container(
            [
                html.H2("Overview"),
                dbc.Alert(
                    (
                        "No trade-flow snapshot found. Run the daily flow with "
                        "--dry-run or --live to populate the dashboard."
                    ),
                    color="secondary",
                ),
            ],
            fluid=True,
            className="mt-4",
        )

    attention = _attention_rows(report, positions, orders)
    return dbc.Container(
        [
            _snapshot_header(plan, report, broker_state),
            _metric_cards(report, positions, orders, attention, broker_state),
            _attention_section(attention),
            dbc.Row(
                [
                    dbc.Col(_position_summary(positions), lg=7),
                    dbc.Col(_order_summary(orders), lg=5),
                ],
                className="g-3 mb-4",
            ),
            _latest_run_section(plan, report),
        ],
        fluid=True,
        className="mt-4",
    )


def _snapshot_header(plan: dict, report: dict, broker_state) -> dbc.Card:
    generated = report.get("generated_at") or plan.get("generated_at") or "-"
    mode = report.get("mode", "-")
    collected = _fmt_value(getattr(broker_state, "collected_at", None))
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div("Operator Overview", className="text-muted small"),
                html.H2("Overview", className="mb-2"),
                html.Div(
                    [
                        _pill("mode", mode),
                        _pill("report", generated),
                        _pill("broker snapshot", collected),
                    ],
                    className="d-flex gap-2 flex-wrap",
                ),
            ]
        ),
        className="mb-3",
    )


def _metric_cards(
    report: dict,
    positions: list[dict],
    orders: list[dict],
    attention: list[dict],
    broker_state,
) -> dbc.Row:
    counts = report.get("counts", {})
    missing_stops = sum(1 for row in positions if row.get("status") == "missing_stop")
    old_stops = sum(1 for row in orders if row.get("role") == "old_position_stops")
    entry_orders = sum(1 for row in orders if row.get("role") == "entry_orders")
    net_liq = "-"
    if broker_state is not None:
        net_liq = _fmt_money(getattr(broker_state.account, "net_liquidation", None))
    items = [
        ("Net Liq", net_liq, "secondary"),
        ("Positions", len(positions), "primary"),
        ("Open Orders", len(orders), "primary"),
        ("Attention", len(attention), "danger" if attention else "success"),
        ("Alerts", counts.get("alerts", len(report.get("alerts", []))), "danger"),
        ("Missing Stops", missing_stops, "danger" if missing_stops else "success"),
        ("Old Stops", old_stops, "warning" if old_stops else "success"),
        ("Entry Orders", entry_orders, "info"),
    ]
    return dbc.Row(
        [
            dbc.Col(_metric_card(label, value, color), xl=3, lg=4, sm=6)
            for label, value, color in items
        ],
        className="g-3 mb-4",
    )


def _metric_card(label: str, value, color: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(label, className="text-muted small"),
                html.H3(str(value), className=f"text-{color} mb-0"),
            ]
        ),
        className="h-100",
    )


def _attention_rows(
    report: dict,
    positions: list[dict],
    orders: list[dict],
) -> list[dict]:
    rows: list[dict] = []
    for alert in report.get("alerts", []):
        rows.append(
            {
                "type": "Alert",
                "item": alert.get("code", "-"),
                "detail": alert.get("message", ""),
                "action": alert.get("operator_action") or "Review alert.",
            }
        )

    for row in positions:
        status = row.get("status")
        if status == "missing_stop":
            rows.append(
                {
                    "type": "Position",
                    "item": row.get("local_symbol") or "-",
                    "detail": f"{row.get('system') or '-'} qty {_fmt_qty(row.get('quantity'))}",
                    "action": "Place or verify the protective stop.",
                }
            )
        elif status == "unknown_system":
            rows.append(
                {
                    "type": "Position",
                    "item": row.get("local_symbol") or "-",
                    "detail": f"{row.get('symbol') or '-'} qty {_fmt_qty(row.get('quantity'))}",
                    "action": "Resolve system attribution.",
                }
            )

    for row in orders:
        role = row.get("role")
        if role == "old_position_stops":
            rows.append(
                {
                    "type": "Order",
                    "item": f"#{row.get('order_id')}",
                    "detail": _order_detail(row),
                    "action": "Review or cancel the old stop.",
                }
            )
        elif role == "other_orders":
            rows.append(
                {
                    "type": "Order",
                    "item": f"#{row.get('order_id')}",
                    "detail": _order_detail(row),
                    "action": "Review unclassified order.",
                }
            )

    for event in report.get("events", []):
        status = str(event.get("status", ""))
        if status.endswith("_threw"):
            rows.append(
                {
                    "type": "Execution",
                    "item": event.get("intent", "-"),
                    "detail": event.get("message") or status,
                    "action": "Review execution error.",
                }
            )
    return rows


def _attention_section(rows: list[dict]) -> dbc.Card:
    if not rows:
        return dbc.Card(
            [
                dbc.CardHeader("Needs Attention"),
                dbc.CardBody(html.Div("No snapshot issues found.", className="text-muted")),
            ],
            className="mb-4",
        )
    return _table_card(
        "Needs Attention",
        ["Type", "Item", "Detail", "Action"],
        [
            html.Tr(
                [
                    html.Td(row["type"]),
                    html.Td(row["item"]),
                    html.Td(row["detail"]),
                    html.Td(row["action"]),
                ]
            )
            for row in rows
        ],
    )


def _position_summary(rows: list[dict]) -> dbc.Card:
    if not rows:
        return _empty_card("Positions", "No positions in the latest snapshot.")
    table_rows = [
        html.Tr(
            [
                html.Td(_POSITION_STATUS_LABELS.get(row.get("status"), "-")),
                html.Td(row.get("system") or "-"),
                html.Td(row.get("local_symbol") or "-"),
                html.Td(_fmt_qty(row.get("quantity"))),
                html.Td(_fmt_money(row.get("unrealized_pnl"), show_plus=True)),
                html.Td(_fmt_money(row.get("current_risk"))),
                html.Td(_fmt_float(row.get("stop_price"))),
            ]
        )
        for row in rows
    ]
    table_rows.append(_position_total_row(rows))
    return _table_card(
        "Positions",
        ["Status", "System", "Contract", "Qty", "Return", "Risk", "Stop"],
        table_rows,
    )


def _position_total_row(rows: list[dict]) -> html.Tr:
    return html.Tr(
        [
            html.Td("Total", className="fw-bold"),
            html.Td("-"),
            html.Td("-"),
            html.Td(_fmt_qty(_sum_known(rows, "quantity")), className="fw-bold"),
            html.Td(
                _fmt_money(_sum_known(rows, "unrealized_pnl"), show_plus=True),
                className="fw-bold",
            ),
            html.Td(_fmt_money(_sum_known(rows, "current_risk")), className="fw-bold"),
            html.Td("-"),
        ],
        className="table-active",
    )


def _order_summary(rows: list[dict]) -> dbc.Card:
    if not rows:
        return _empty_card("Orders", "No open orders in the latest snapshot.")

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get("role") or "other_orders", []).append(row)
    role_order = [
        "entry_orders",
        "entry_bracket_stops",
        "current_position_stops",
        "old_position_stops",
        "other_orders",
    ]
    table_rows = []
    for role in role_order:
        role_rows = grouped.get(role, [])
        if not role_rows:
            continue
        symbols = sorted({row.get("symbol") or "-" for row in role_rows})
        table_rows.append(
            html.Tr(
                [
                    html.Td(_ORDER_ROLE_LABELS.get(role, "Other Orders")),
                    html.Td(len(role_rows)),
                    html.Td(", ".join(symbols)),
                ]
            )
        )
    return _table_card("Orders", ["Group", "Count", "Symbols"], table_rows)


def _latest_run_section(plan: dict, report: dict) -> dbc.Card:
    counts = report.get("counts", {})
    rows = [
        ("Trade candidates", len(plan.get("signals", []))),
        ("Planned actions", len(plan.get("intents", []))),
        ("Orders sent", counts.get("submitted", 0)),
        ("Roll orders sent", counts.get("roll_submitted", 0)),
        ("Cancel requests", counts.get("cancel_requested", 0)),
        ("Stop updates", counts.get("modified", 0)),
        ("Operator alerts", counts.get("alerts", len(report.get("alerts", [])))),
        ("Report-only items", counts.get("reported_only", 0)),
        ("Dry-run actions", counts.get("dry_run", 0)),
        ("Skipped candidates", counts.get("skipped", len(plan.get("skipped", [])))),
        ("Execution errors", counts.get("threw", 0)),
    ]
    return _table_card(
        "Latest Run",
        ["Item", "Count"],
        [html.Tr([html.Td(label), html.Td(value)]) for label, value in rows],
    )


def _table_card(title: str, headers: list[str], rows: list) -> dbc.Card:
    return dbc.Card(
        [
            dbc.CardHeader(title),
            dbc.CardBody(
                dbc.Table(
                    [
                        html.Thead(html.Tr([html.Th(header) for header in headers])),
                        html.Tbody(rows),
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


def _empty_card(title: str, text: str) -> dbc.Card:
    return dbc.Card(
        [dbc.CardHeader(title), dbc.CardBody(html.Div(text, className="text-muted"))],
        className="mb-4",
    )


def _pill(label: str, value) -> html.Span:
    return html.Span(
        f"{label}: {value}",
        className="badge rounded-pill bg-secondary",
        style={"fontSize": "0.78rem"},
    )


def _order_detail(row: dict) -> str:
    parts = [
        row.get("system") or "-",
        row.get("symbol") or "-",
        row.get("local_symbol") or "-",
        row.get("action") or "-",
        row.get("order_type") or "-",
        f"qty {_fmt_qty(row.get('quantity'))}",
    ]
    price = row.get("aux_price") or row.get("limit_price")
    if price is not None:
        parts.append(f"price {_fmt_float(price)}")
    return " | ".join(parts)


def _fmt_value(value) -> str:
    if value is None:
        return "-"
    return str(value)


def _sum_known(rows: list[dict], key: str) -> float | None:
    values = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return sum(values)


def _fmt_float(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.4f}"
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
