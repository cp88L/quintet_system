"""Recent broker fills grouped by operator workflow."""

from __future__ import annotations

import dash
from dash import html
import dash_bootstrap_components as dbc

from quintet.config import EXECUTION_LOOKBACK_HOURS
from quintet.dashboard.data.loader import (
    load_fill_rows,
    load_latest_execution_report,
)

dash.register_page(__name__, path="/fills", name="Fills", order=5)

_ROLE_ORDER = ["entry_fills", "exit_fills", "roll_fills", "other_fills"]
_ROLE_LABELS = {
    "entry_fills": "Entries",
    "exit_fills": "Exits",
    "roll_fills": "Rolls",
    "other_fills": "Other Recent Fills",
}


def layout() -> dbc.Container:
    rows = load_fill_rows()
    report = load_latest_execution_report()
    return dbc.Container(
        [
            _summary_card(rows, report),
            _fill_totals_table(rows, report),
        ],
        fluid=True,
        className="mt-4",
    )


def _summary_card(rows: list[dict], report: dict) -> dbc.Card:
    generated = report.get("generated_at") or "-"
    totals = _fill_totals(rows, report)
    ordered = _sum_total(totals, "ordered")
    filled = _sum_total(totals, "filled")
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div("Recent broker fills", className="text-muted small"),
                html.H2("Fills", className="mb-2"),
                html.Div(
                    [
                        _pill("ordered", _fmt_qty(ordered)),
                        _pill("filled", _fmt_qty(filled)),
                        _pill("lookback hours", EXECUTION_LOOKBACK_HOURS),
                        _pill("report", generated),
                    ],
                    className="d-flex gap-2 flex-wrap",
                ),
            ]
        ),
        className="mb-3",
    )


def _fill_totals_table(rows: list[dict], report: dict) -> dbc.Card:
    totals = _fill_totals(rows, report)
    if not any(row["ordered"] is not None or row["filled"] for row in totals):
        return _empty_card("Fill Totals", "No recent fills in the latest snapshot.")

    table_rows = [
        html.Tr(
            [
                html.Td(row["label"]),
                html.Td(_fmt_qty(row["ordered"])),
                html.Td(_fmt_qty(row["filled"])),
                html.Td(_fmt_qty(row["remaining"])),
                html.Td(row["status"]),
            ]
        )
        for row in totals
        if row["ordered"] is not None or row["filled"]
    ]
    return dbc.Card(
        [
            dbc.CardHeader("Fill Totals"),
            dbc.CardBody(
                dbc.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Workflow"),
                                    html.Th("Ordered"),
                                    html.Th("Filled"),
                                    html.Th("Remaining"),
                                    html.Th("Status"),
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


def _fill_totals(rows: list[dict], report: dict) -> list[dict]:
    ordered = _ordered_quantities(report)
    filled = {role: 0.0 for role in _ROLE_ORDER}
    for row in rows:
        role = row.get("role") or "other_fills"
        filled[role] = filled.get(role, 0.0) + _numeric(row.get("quantity"), 0.0)
    return [
        _total_row(role, ordered.get(role), filled.get(role, 0.0))
        for role in _ROLE_ORDER
    ]


def _ordered_quantities(report: dict) -> dict[str, float | None]:
    ordered: dict[str, float | None] = {role: None for role in _ROLE_ORDER}
    for record in report.get("submitted", []):
        status = str(record.get("status") or "")
        intent = record.get("intent") or {}
        if status == "submitted":
            _add_ordered(ordered, "entry_fills", _intent_quantity(intent))
        elif status == "exit_submitted":
            _add_ordered(ordered, "exit_fills", _intent_quantity(intent))
        elif status == "roll_submitted":
            closeout_qty = _intent_quantity(intent)
            roll_qty = _numeric((record.get("roll_summary") or {}).get("quantity"))
            if closeout_qty is not None:
                _add_ordered(ordered, "roll_fills", closeout_qty)
            if roll_qty is not None:
                _add_ordered(ordered, "roll_fills", roll_qty)
    return ordered


def _intent_quantity(intent: dict) -> float | None:
    return _numeric(intent.get("quantity"))


def _add_ordered(
    totals: dict[str, float | None],
    role: str,
    quantity: float | None,
) -> None:
    if quantity is None:
        return
    totals[role] = (totals.get(role) or 0.0) + quantity


def _total_row(role: str, ordered: float | None, filled: float) -> dict:
    remaining = None if ordered is None else ordered - filled
    return {
        "label": _ROLE_LABELS.get(role, "Other Recent Fills"),
        "ordered": ordered,
        "filled": filled,
        "remaining": remaining,
        "status": _fill_status(ordered, filled),
    }


def _fill_status(ordered: float | None, filled: float) -> str:
    if ordered is None:
        return "recent fills only" if filled else "-"
    remaining = ordered - filled
    if remaining == 0:
        return "complete"
    if filled == 0:
        return "not filled"
    if remaining > 0:
        return "partial"
    return "extra recent fills"


def _sum_total(rows: list[dict], key: str) -> float:
    total = 0.0
    for row in rows:
        value = row.get(key)
        if value is not None:
            total += _numeric(value, 0.0)
    return total


def _empty_card(title: str, text: str) -> dbc.Card:
    return dbc.Card(
        [
            dbc.CardHeader(title),
            dbc.CardBody(html.Div(text, className="text-muted")),
        ],
        className="mb-4",
    )


def _pill(label: str, value) -> html.Span:
    return html.Span(
        f"{label}: {value}",
        className="badge rounded-pill bg-secondary",
        style={"fontSize": "0.78rem"},
    )


def _numeric(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
