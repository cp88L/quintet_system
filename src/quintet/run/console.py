"""Console formatting for the daily run."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from quintet.broker.models import BrokerError, BrokerOrder, BrokerPosition, BrokerState
from quintet.execution.models import ExecutionEvent, ExecutionReport
from quintet.trading.models import SignalCandidate, TradePlan
from quintet.trading.reconcile import reconcile_state


def print_trade_report(
    *,
    broker_state: BrokerState,
    plan: TradePlan,
    report: ExecutionReport,
    report_dir: Path,
) -> None:
    """Print the broker-state, trade-plan, and execution-report summary."""
    for line in format_trade_report(
        broker_state=broker_state,
        plan=plan,
        report=report,
        report_dir=report_dir,
    ):
        print(line)


def format_trade_report(
    *,
    broker_state: BrokerState,
    plan: TradePlan,
    report: ExecutionReport,
    report_dir: Path,
) -> list[str]:
    """Build the operator-facing Step 8 console output."""
    reconciled = reconcile_state(broker_state)
    signal_by_key = {signal.key: signal for signal in plan.signals}
    intent_counts = Counter(intent.__class__.__name__ for intent in plan.intents)
    signal_counts = Counter(signal.system for signal in plan.signals)

    lines = [
        (
            f"  broker state: equity={broker_state.account.net_liquidation:.2f} "
            f"positions={len(broker_state.positions)} "
            f"open_orders={len(broker_state.open_orders)} "
            f"fills={len(broker_state.recent_fills)} "
            f"errors={len(broker_state.recent_errors)}"
        ),
        (
            "  current state: "
            f"held={len(reconciled.positions_by_key)} "
            f"pending_entries={len(reconciled.entry_orders_by_key)} "
            f"protective_stops={len(reconciled.protective_stops_by_key)} "
            f"orphaned_stops={len(reconciled.orphaned_orders)} "
            f"missing_stops={len(reconciled.positions_without_protective_stop)} "
            f"unknown_positions={len(reconciled.unknown_system_positions)} "
            f"external_orders={len(reconciled.external_or_unclassified_orders)}"
        ),
        f"  signals: {len(plan.signals)}{_counter_suffix(signal_counts)}",
        f"  intents: {len(plan.intents)}{_counter_suffix(intent_counts)}",
        (
            "  execution: "
            f"mode={report.mode} "
            f"submitted={report.counts.submitted} "
            f"roll_submitted={report.counts.roll_submitted} "
            f"cancel_requested={report.counts.cancel_requested} "
            f"modified={report.counts.modified} "
            f"reported_only={report.counts.reported_only} "
            f"alerts={report.counts.alerts} "
            f"threw={report.counts.threw} "
            f"dry_run={report.counts.dry_run} "
            f"skipped={report.counts.skipped}"
        ),
    ]

    lines.extend(_position_lines(broker_state.positions))
    lines.extend(_order_lines(broker_state.open_orders))
    lines.extend(_broker_error_lines(broker_state.recent_errors))
    lines.extend(_bracket_lines(report.submitted, signal_by_key))
    lines.extend(_maintenance_lines(report.submitted))
    lines.extend(_skipped_lines(plan.skipped or report.skipped))
    lines.extend(_alert_lines(report.alerts))
    lines.extend(_event_lines(report.events))
    lines.append(f"  wrote {report_dir / 'latest_trade_plan.json'}")
    lines.append(f"  wrote {report_dir / 'latest_execution_report.json'}")
    return lines


def _counter_suffix(counter: Counter) -> str:
    if not counter:
        return ""
    parts = [f"{key}={counter[key]}" for key in sorted(counter)]
    return " (" + ", ".join(parts) + ")"


def _position_lines(positions: Iterable[BrokerPosition]) -> list[str]:
    rows = list(positions)
    if not rows:
        return []
    lines = [
        "",
        "  Open positions:",
        (
            f"  {'contract':<14} {'symbol':<8} {'qty':>8} "
            f"{'avg_cost':>12} {'market':>12} {'value':>14}"
        ),
    ]
    for position in rows:
        lines.append(
            f"  {position.local_symbol:<14} {position.symbol:<8} "
            f"{_fmt_float(position.quantity):>8} "
            f"{_fmt_float(position.avg_cost):>12} "
            f"{_fmt_float(position.market_price):>12} "
            f"{_fmt_float(position.market_value):>14}"
        )
    return lines


def _order_lines(orders: Iterable[BrokerOrder]) -> list[str]:
    rows = list(orders)
    if not rows:
        return []
    lines = [
        "",
        "  Open orders:",
        (
            f"  {'id':>8} {'sys':<5} {'contract':<14} {'action':<6} "
            f"{'type':<8} {'qty':>5} {'aux':>12} {'limit':>12} "
            f"{'parent':>8} {'status':<14}"
        ),
    ]
    for order in rows:
        lines.append(
            f"  {order.order_id:>8} {(order.system or '-'):5} "
            f"{order.local_symbol:<14} {_value(order.action):<6} "
            f"{_value(order.order_type):<8} {order.quantity:>5} "
            f"{_fmt_float(order.aux_price):>12} "
            f"{_fmt_float(order.limit_price):>12} "
            f"{str(order.parent_id or '-'):>8} {_value(order.status):<14}"
        )
    return lines


def _broker_error_lines(errors: Iterable[BrokerError]) -> list[str]:
    rows = list(errors)
    if not rows:
        return []
    lines = [
        "",
        "  Broker messages:",
        f"  {'severity':<8} {'code':>6} message",
    ]
    for error in rows:
        lines.append(
            f"  {_value(error.severity):<8} {error.code:>6} {error.message}"
        )
    return lines


def _bracket_lines(
    records: list[dict],
    signal_by_key: dict[tuple[int, str], SignalCandidate],
) -> list[str]:
    rows = [
        record
        for record in records
        if _is_bracket_intent(record.get("intent", {}))
    ]
    if not rows:
        return ["", "  New bracket entries: none"]

    lines = [
        "",
        "  New bracket entries:",
        (
            f"  {'sys':<5} {'contract':<14} {'exch':<8} {'side':<5} "
            f"{'qty':>4} {'prob':>7} {'tau':>7} {'cl':>4} "
            f"{'entry':>12} {'stop':>12} {'risk':>12} {'status/order_ids':<18}"
        ),
    ]
    for record in rows:
        intent = record["intent"]
        key = _key_tuple(intent.get("key"))
        signal = signal_by_key.get(key) if key is not None else None
        system = key[1] if key is not None else "-"
        lines.append(
            f"  {system:<5} {intent.get('local_symbol', '-'):<14} "
            f"{intent.get('exchange', '-'):<8} {intent.get('side', '-'):<5} "
            f"{intent.get('quantity', 0):>4} "
            f"{_fmt_float(getattr(signal, 'prob', None), digits=4):>7} "
            f"{_fmt_float(getattr(signal, 'tau', None), digits=4):>7} "
            f"{_fmt_int(getattr(signal, 'cluster_id', None)):>4} "
            f"{_fmt_float(intent.get('entry_stop_price')):>12} "
            f"{_fmt_float(intent.get('protective_stop_price')):>12} "
            f"{_fmt_float(intent.get('total_risk')):>12} "
            f"{_record_status(record):<18}"
        )
    return lines


def _maintenance_lines(records: list[dict]) -> list[str]:
    rows = [
        record
        for record in records
        if not _is_bracket_intent(record.get("intent", {}))
    ]
    if not rows:
        return ["", "  Maintenance / existing-position actions: none"]

    lines = [
        "",
        "  Maintenance / existing-position actions:",
        f"  {'status/order_ids':<18} {'sys':<5} {'contract':<14} {'action':<18} details",
    ]
    for record in rows:
        intent = record.get("intent", {})
        key = _key_tuple(intent.get("key") or intent.get("old_key"))
        system = key[1] if key is not None else "-"
        lines.append(
            f"  {_record_status(record):<18} {system:<5} "
            f"{_intent_contract(intent):<14} "
            f"{_intent_action(intent):<18} {_intent_details(intent, record)}"
        )
    return lines


def _skipped_lines(skipped: list[dict]) -> list[str]:
    if not skipped:
        return ["", "  Skipped signals: none"]
    lines = [
        "",
        "  Skipped signals:",
        f"  {'sys':<5} {'contract':<14} {'symbol':<8} reason",
    ]
    for item in skipped:
        key = _key_tuple(item.get("key"))
        system = key[1] if key is not None else "-"
        lines.append(
            f"  {system:<5} {item.get('local_symbol', '-'):<14} "
            f"{item.get('symbol', '-'):<8} {item.get('reason', '-')}"
        )
    return lines


def _alert_lines(alerts: list[dict]) -> list[str]:
    if not alerts:
        return ["", "  Alerts: none"]
    lines = [
        "",
        "  Alerts:",
        f"  {'level':<8} {'code':<24} {'key':<18} message",
    ]
    for alert in alerts:
        action = alert.get("operator_action")
        message = alert.get("message", "")
        if action:
            message = f"{message} | action: {action}"
        lines.append(
            f"  {alert.get('level', 'warning'):<8} "
            f"{alert.get('code', '-'):<24} "
            f"{_fmt_key(alert.get('key')):<18} {message}"
        )
    return lines


def _event_lines(events: list[ExecutionEvent]) -> list[str]:
    if not events:
        return []
    lines = [
        "",
        "  Execution events:",
        f"  {'status':<16} {'order_id':>8} {'key':<18} {'intent':<22} message",
    ]
    for event in events:
        lines.append(
            f"  {_value(event.status):<16} {str(event.order_id or '-'):>8} "
            f"{_fmt_key(event.key):<18} {event.intent:<22} {event.message or ''}"
        )
    return lines


def _is_bracket_intent(intent: dict) -> bool:
    return "entry_order_type" in intent and "protective_order_type" in intent


def _key_tuple(value: object) -> tuple[int, str] | None:
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2:
        return (int(value[0]), str(value[1]))
    if isinstance(value, list) and len(value) == 2:
        return (int(value[0]), str(value[1]))
    return None


def _fmt_key(value: object) -> str:
    key = _key_tuple(value)
    if key is None:
        return "-"
    return f"{key[1]}:{key[0]}"


def _fmt_int(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _fmt_float(value: object, *, digits: int = 6) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _record_status(record: dict) -> str:
    ids = _record_order_ids(record)
    status = str(record.get("status", "-"))
    if ids:
        return f"{status} {ids}"
    return status


def _record_order_ids(record: dict) -> str:
    if "order_ids" in record:
        return "[" + ",".join(str(i) for i in record["order_ids"]) + "]"
    if "order_id" in record:
        return str(record["order_id"])
    ids = []
    ids.extend(record.get("closeout_order_ids", []))
    ids.extend(record.get("roll_order_ids", []))
    if ids:
        return "[" + ",".join(str(i) for i in ids) + "]"
    return ""


def _intent_contract(intent: dict) -> str:
    return (
        intent.get("local_symbol")
        or intent.get("old_local_symbol")
        or intent.get("new_local_symbol")
        or "-"
    )


def _intent_action(intent: dict) -> str:
    if "oca_group" in intent:
        return "last_day_closeout"
    if "new_local_symbol" in intent:
        return "roll_entry"
    if "aux_price" in intent or "limit_price" in intent:
        return "modify_order"
    if "order_id" in intent:
        return "cancel_order"
    if "quantity" in intent and "local_symbol" in intent:
        return "exit_position"
    return intent.get("reason", "reported")


def _intent_details(intent: dict, record: dict) -> str:
    action = _intent_action(intent)
    if action == "last_day_closeout":
        parts = [
            f"close qty={intent.get('quantity')}",
            f"oca={intent.get('oca_group')}",
        ]
        stop = intent.get("protective_stop") or {}
        if stop:
            parts.append(
                "replace stop "
                f"order={stop.get('order_id')} "
                f"aux={_fmt_float(stop.get('aux_price'))}"
            )
        roll = intent.get("roll_entry")
        if roll:
            parts.append(
                "roll "
                f"{roll.get('old_local_symbol')}->{roll.get('new_local_symbol')} "
                f"rspos={_fmt_float(roll.get('rspos'), digits=4)} "
                f"stop={_fmt_float(roll.get('protective_stop_price'))}"
            )
        return "; ".join(parts)
    if action == "modify_order":
        return (
            f"order={intent.get('order_id')} "
            f"aux->{_fmt_float(intent.get('aux_price'))} "
            f"limit->{_fmt_float(intent.get('limit_price'))} "
            f"reason={intent.get('reason', '-')}"
        )
    if action == "cancel_order":
        return f"order={intent.get('order_id')} reason={intent.get('reason', '-')}"
    if action == "exit_position":
        return f"qty={intent.get('quantity')} reason={intent.get('reason', '-')}"
    if action == "roll_entry":
        return (
            f"{intent.get('old_local_symbol')}->{intent.get('new_local_symbol')} "
            f"qty={intent.get('quantity')} "
            f"rspos={_fmt_float(intent.get('rspos'), digits=4)} "
            f"threshold={_fmt_float(intent.get('threshold'), digits=4)}"
        )
    summary = record.get("roll_summary")
    if summary:
        return str(summary)
    return f"reason={intent.get('reason', '-')}"
