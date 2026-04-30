"""Trade-flow report viewer."""

from __future__ import annotations

import dash
from dash import html
import dash_bootstrap_components as dbc

from quintet.dashboard.data.loader import (
    load_latest_execution_report,
    load_latest_trade_plan,
)

dash.register_page(__name__, path="/trade", name="Trade Reports", order=3)


def layout() -> dbc.Container:
    plan = load_latest_trade_plan()
    report = load_latest_execution_report()
    if not plan and not report:
        return dbc.Container(
            [
                html.H2("Trade Reports"),
                dbc.Alert(
                    (
                        "No trade-flow reports found. Run the daily flow with "
                        "--dry-run or --live to create latest_trade_plan.json "
                        "and latest_execution_report.json."
                    ),
                    color="secondary",
                ),
            ],
            fluid=True,
            className="mt-4",
        )

    return dbc.Container(
        [
            html.H2("Trade Reports"),
            _run_header(plan, report),
            _count_cards(report),
            _alerts_section(report),
            _reported_only_section(plan, report),
            _submitted_section(report),
            _skipped_section(plan),
        ],
        fluid=True,
        className="mt-4",
    )


def _run_header(plan: dict, report: dict) -> dbc.Card:
    generated = report.get("generated_at") or plan.get("generated_at") or "-"
    mode = report.get("mode", "-")
    signals = len(plan.get("signals", []))
    intents = len(plan.get("intents", []))
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div("Latest run", className="text-muted small"),
                html.H4(f"{mode} | {generated}", className="mb-2"),
                html.Div(
                    [
                        _pill("signals", signals),
                        _pill("intents", intents),
                    ],
                    className="d-flex gap-2 flex-wrap",
                ),
            ]
        ),
        className="mb-3",
    )


def _count_cards(report: dict) -> dbc.Row:
    counts = report.get("counts", {})
    items = [
        ("submitted", counts.get("submitted", 0), "success"),
        ("roll submitted", counts.get("roll_submitted", 0), "primary"),
        ("cancel requested", counts.get("cancel_requested", 0), "warning"),
        ("modified", counts.get("modified", 0), "info"),
        ("reported only", counts.get("reported_only", 0), "secondary"),
        ("alerts", counts.get("alerts", 0), "danger"),
        ("threw", counts.get("threw", 0), "danger"),
        ("dry run", counts.get("dry_run", 0), "secondary"),
        ("skipped", counts.get("skipped", 0), "secondary"),
    ]
    return dbc.Row(
        [
            dbc.Col(_count_card(label, value, color), lg=3, md=4, sm=6)
            for label, value, color in items
        ],
        className="g-3 mb-4",
    )


def _alerts_section(report: dict) -> dbc.Card:
    alerts = report.get("alerts", [])
    if not alerts:
        return _empty_section("Alerts", "No alert intents in the latest report.")

    rows = [
        html.Tr(
            [
                html.Td(alert.get("level", "warning")),
                html.Td(alert.get("code", "-")),
                html.Td(_format_key(alert.get("key"))),
                html.Td(alert.get("message", "")),
                html.Td(_alert_action(alert)),
            ]
        )
        for alert in alerts
    ]
    return _table_section(
        "Alerts",
        ["level", "code", "key", "message", "operator action"],
        rows,
    )


def _reported_only_section(plan: dict, report: dict) -> dbc.Card:
    events = [
        event
        for event in report.get("events", [])
        if event.get("status") == "reported"
    ]
    rolls = _roll_intents(plan)
    if not events and not rolls:
        return _empty_section(
            "Reported Only",
            "No report-only intents in the latest report.",
        )

    children: list = []
    if events:
        children.append(
            _inline_table(
                ["intent", "key", "message"],
                [
                    html.Tr(
                        [
                            html.Td(event.get("intent", "-")),
                            html.Td(_format_key(event.get("key"))),
                            html.Td(event.get("message", "")),
                        ]
                    )
                    for event in events
                ],
            )
        )
    if rolls:
        children.append(html.H6("Roll candidates", className="mt-3"))
        children.append(
            _inline_table(
                [
                    "system",
                    "symbol",
                    "old",
                    "new",
                    "qty",
                    "RSpos",
                    "threshold",
                    "stop",
                    "operator action",
                ],
                [_roll_row(intent) for intent in rolls],
            )
        )

    return dbc.Card(
        [
            dbc.CardHeader("Reported Only"),
            dbc.CardBody(children),
        ],
        className="mb-4",
    )


def _submitted_section(report: dict) -> dbc.Card:
    submitted = report.get("submitted", [])
    if not submitted:
        return _empty_section(
            "Submitted / Requested",
            "No submitted, cancel-requested, or modified records.",
        )

    rows = []
    for record in submitted:
        intent = record.get("intent", {})
        rows.append(
            html.Tr(
                [
                    html.Td(record.get("status", "-")),
                    html.Td(record.get("order_id") or _format_order_ids(record)),
                    html.Td(_format_key(intent.get("key"))),
                    html.Td(intent.get("symbol", "")),
                    html.Td(_submitted_contract(record, intent)),
                    html.Td(_submitted_roll_details(record)),
                    html.Td(intent.get("reason", "")),
                ]
            )
        )
    return _table_section(
        "Submitted / Requested",
        [
            "status",
            "order id(s)",
            "key",
            "symbol",
            "contract / roll",
            "roll details",
            "reason",
        ],
        rows,
    )


def _skipped_section(plan: dict) -> dbc.Card:
    skipped = plan.get("skipped", [])
    if not skipped:
        return _empty_section("Skipped", "No skipped trade candidates.")
    rows = [
        html.Tr(
            [
                html.Td(_format_key(item.get("key"))),
                html.Td(item.get("symbol", "")),
                html.Td(item.get("reason", "")),
            ]
        )
        for item in skipped
    ]
    return _table_section("Skipped", ["key", "symbol", "reason"], rows)


def _roll_intents(plan: dict) -> list[dict]:
    return [
        intent
        for intent in plan.get("intents", [])
        if intent.get("reason") == "last_day_roll"
        or {"old_key", "new_key", "new_local_symbol"}.issubset(intent)
    ]


def _roll_row(intent: dict) -> html.Tr:
    return html.Tr(
        [
            html.Td(_system_from_key(intent.get("new_key"))),
            html.Td(intent.get("symbol", "")),
            html.Td(intent.get("old_local_symbol", "")),
            html.Td(intent.get("new_local_symbol", "")),
            html.Td(intent.get("quantity", "")),
            html.Td(_format_float(intent.get("rspos"))),
            html.Td(_format_float(intent.get("threshold"))),
            html.Td(_format_float(intent.get("protective_stop_price"))),
            html.Td(
                "Review roll candidate; no live roll order was submitted for this record."
            ),
        ]
    )


def _table_section(title: str, headings: list[str], rows: list) -> dbc.Card:
    return dbc.Card(
        [
            dbc.CardHeader(title),
            dbc.CardBody(_inline_table(headings, rows)),
        ],
        className="mb-4",
    )


def _inline_table(headings: list[str], rows: list) -> dbc.Table:
    return dbc.Table(
        [
            html.Thead(html.Tr([html.Th(heading) for heading in headings])),
            html.Tbody(rows),
        ],
        bordered=False,
        hover=True,
        responsive=True,
        size="sm",
        className="mb-0",
    )


def _empty_section(title: str, message: str) -> dbc.Card:
    return dbc.Card(
        [
            dbc.CardHeader(title),
            dbc.CardBody(html.Div(message, className="text-muted")),
        ],
        className="mb-4",
    )


def _count_card(label: str, value: int, color: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(label.upper(), className="text-muted small"),
                html.H3(str(value), className=f"text-{color} mb-0"),
            ]
        ),
        className="h-100",
    )


def _pill(label: str, value: int) -> html.Span:
    return html.Span(
        f"{label}: {value}",
        className="badge rounded-pill text-bg-secondary",
    )


def _alert_action(alert: dict) -> str:
    operator_action = alert.get("operator_action")
    if operator_action:
        return operator_action
    code = alert.get("code", "")
    actions = {
        "external_or_unclassified_order": "Review outside order; no action sent.",
        "missing_last_day_metadata": "Fix contract metadata before relying on exits.",
        "missing_protective_stop": "Verify or place the protective stop manually.",
        "roll_candidate_missing": "Review current-contract funnel data.",
        "roll_contract_not_advanced": "Wait for the active contract to advance.",
        "roll_not_eligible": "No action; RSpos is below the roll threshold.",
        "roll_rspos_missing": "Review processed signal data for RSpos.",
        "roll_stop_missing": "Review support/resistance data for the stop.",
        "unknown_system_position": "Review manual position attribution.",
    }
    return actions.get(code, "Review before live order submission.")


def _format_key(key) -> str:
    if isinstance(key, list) and len(key) == 2:
        return f"{key[0]} / {key[1]}"
    if isinstance(key, tuple) and len(key) == 2:
        return f"{key[0]} / {key[1]}"
    return "-"


def _system_from_key(key) -> str:
    if isinstance(key, (list, tuple)) and len(key) == 2:
        return str(key[1])
    return "-"


def _format_order_ids(record: dict) -> str:
    ids = record.get("order_ids")
    if isinstance(ids, list):
        return ", ".join(str(order_id) for order_id in ids)
    parts = []
    cancelled = record.get("cancelled_stop_order_id")
    if cancelled:
        parts.append(f"cancel {cancelled}")
    closeout_ids = record.get("closeout_order_ids")
    if isinstance(closeout_ids, list):
        parts.append(
            "closeout " + ", ".join(str(order_id) for order_id in closeout_ids)
        )
    roll_ids = record.get("roll_order_ids")
    if isinstance(roll_ids, list) and roll_ids:
        parts.append("roll " + ", ".join(str(order_id) for order_id in roll_ids))
    if parts:
        return "; ".join(parts)
    return ""


def _submitted_contract(record: dict, intent: dict) -> str:
    summary = _roll_summary(record)
    if summary:
        return f"{summary.get('old_contract', '')} -> {summary.get('new_contract', '')}"
    return intent.get("local_symbol", "")


def _submitted_roll_details(record: dict) -> str:
    summary = _roll_summary(record)
    if not summary:
        return "-"
    return (
        f"qty {summary.get('quantity', '')} | "
        f"RSpos {_format_float(summary.get('rspos'))} | "
        f"threshold {_format_float(summary.get('threshold'))} | "
        f"stop {_format_float(summary.get('protective_stop_price'))}"
    )


def _roll_summary(record: dict) -> dict | None:
    summary = record.get("roll_summary")
    if isinstance(summary, dict):
        return summary
    intent = record.get("intent", {})
    if not isinstance(intent, dict):
        return None
    roll = intent.get("roll_entry")
    if not isinstance(roll, dict):
        return None
    return {
        "old_contract": roll.get("old_local_symbol"),
        "new_contract": roll.get("new_local_symbol"),
        "quantity": roll.get("quantity"),
        "rspos": roll.get("rspos"),
        "threshold": roll.get("threshold"),
        "protective_stop_price": roll.get("protective_stop_price"),
    }


def _format_float(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)
