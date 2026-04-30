"""Console formatting for the daily run."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from quintet.broker.models import BrokerError, BrokerOrder, BrokerPosition, BrokerState
from quintet.execution.models import ExecutionEvent, ExecutionReport
from quintet.trading.models import ReconciledTradeState, SignalCandidate, TradePlan
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

    lines = [
        (
            f"  Account: {_fmt_cash(broker_state.account.net_liquidation)} "
            f"| broker positions={len(broker_state.positions)} "
            f"| open orders={len(broker_state.open_orders)} "
            f"| fills={len(broker_state.recent_fills)} "
            f"| broker messages={len(broker_state.recent_errors)}"
        ),
        f"  State: {_state_summary(reconciled)}",
        f"  Plan: {_plan_summary(plan)}",
        f"  Execution: {_execution_summary(report)}",
        f"  IBKR messages: {_broker_message_summary(broker_state.recent_errors)}",
    ]

    lines.extend(_position_lines(broker_state.positions))
    lines.extend(_order_lines(broker_state.open_orders))
    lines.extend(_broker_error_lines(broker_state.recent_errors))
    lines.extend(_bracket_lines(report.submitted, signal_by_key, mode=report.mode))
    lines.extend(_maintenance_lines(report.submitted))
    lines.extend(_skipped_lines(plan.skipped or report.skipped))
    lines.extend(_alert_lines(report.alerts))
    lines.extend(_event_lines(report.events))
    lines.append(f"  wrote {report_dir / 'latest_trade_plan.json'}")
    lines.append(f"  wrote {report_dir / 'latest_execution_report.json'}")
    return lines


def _state_summary(reconciled: ReconciledTradeState) -> str:
    counts = {
        "held": len(reconciled.positions_by_key),
        "pending entries": len(reconciled.entry_orders_by_key),
        "protective stops": len(reconciled.protective_stops_by_key),
        "orphaned stops": len(reconciled.orphaned_orders),
        "missing stops": len(reconciled.positions_without_protective_stop),
        "unknown positions": len(reconciled.unknown_system_positions),
        "external orders": len(reconciled.external_or_unclassified_orders),
    }
    if not any(counts.values()):
        return "flat; no classified positions or orders"
    return ", ".join(f"{label}={value}" for label, value in counts.items())


def _plan_summary(plan: TradePlan) -> str:
    signal_counts = Counter(signal.system for signal in plan.signals)
    intent_counts = Counter(_intent_label(intent.__class__.__name__) for intent in plan.intents)
    parts = [
        f"{len(plan.signals)} actionable signal(s){_counter_suffix(signal_counts)}",
        f"{len(plan.intents)} intent(s){_counter_suffix(intent_counts)}",
    ]
    if plan.skipped:
        parts.append(f"{len(plan.skipped)} skipped")
    return " -> ".join(parts)


def _execution_summary(report: ExecutionReport) -> str:
    if report.mode == "dry_run":
        prefix = f"dry run only; {report.counts.dry_run} action(s), no orders submitted"
    else:
        prefix = (
            f"live; submitted={report.counts.submitted}, "
            f"rolls={report.counts.roll_submitted}, "
            f"cancels={report.counts.cancel_requested}, "
            f"modifies={report.counts.modified}"
        )
    suffix = (
        f"; skipped={report.counts.skipped}, alerts={report.counts.alerts}, "
        f"threw={report.counts.threw}, reported_only={report.counts.reported_only}"
    )
    return prefix + suffix


def _broker_message_summary(errors: Iterable[BrokerError]) -> str:
    rows = list(errors)
    if not rows:
        return "none"
    info_count = sum(1 for error in rows if _is_info_message(error))
    action_count = len(rows) - info_count
    if action_count == 0:
        return f"{info_count} info message(s) suppressed; 0 warnings/errors"
    return f"{info_count} info suppressed; {action_count} warning/error message(s) below"


def _counter_suffix(counter: Counter) -> str:
    if not counter:
        return ""
    parts = [f"{key}={counter[key]}" for key in sorted(counter)]
    return " (" + ", ".join(parts) + ")"


def _position_lines(positions: Iterable[BrokerPosition]) -> list[str]:
    rows = list(positions)
    if not rows:
        return []
    lines = ["", "  Open positions:"]
    for position in rows:
        lines.append(
            f"    - {position.local_symbol} ({position.symbol}) "
            f"qty={_fmt_float(position.quantity)} "
            f"avg={_fmt_float(position.avg_cost)} "
            f"market={_fmt_float(position.market_price)} "
            f"value={_fmt_cash(position.market_value, symbol=False)}"
        )
    return lines


def _order_lines(orders: Iterable[BrokerOrder]) -> list[str]:
    rows = list(orders)
    if not rows:
        return []
    lines = ["", "  Open orders:"]
    for order in rows:
        limit = ""
        if order.limit_price is not None:
            limit = f" limit={_fmt_float(order.limit_price)}"
        lines.append(
            f"    - #{order.order_id} {(order.system or 'external')} "
            f"{order.local_symbol}: {_value(order.action)} {order.quantity} "
            f"{_value(order.order_type)} aux={_fmt_float(order.aux_price)}"
            f"{limit} parent={order.parent_id or '-'} status={_value(order.status)}"
        )
    return lines


def _broker_error_lines(errors: Iterable[BrokerError]) -> list[str]:
    rows = [error for error in errors if not _is_info_message(error)]
    if not rows:
        return []
    lines = [
        "",
        "  IBKR warnings/errors:",
    ]
    for error in rows:
        lines.append(
            f"    - {_value(error.severity)} {error.code}: {error.message}"
        )
    return lines


def _bracket_lines(
    records: list[dict],
    signal_by_key: dict[tuple[int, str], SignalCandidate],
    *,
    mode: str,
) -> list[str]:
    rows = [
        record
        for record in records
        if _is_bracket_intent(record.get("intent", {}))
    ]
    if not rows:
        return ["", "  New entries: none"]

    mode_label = (
        "dry run - no orders submitted"
        if mode == "dry_run"
        else "live submission results"
    )
    order_type_label = _bracket_order_type_label(rows)
    lines = [
        "",
        f"  New entries ({mode_label}{order_type_label}):",
    ]
    for record in rows:
        intent = record["intent"]
        key = _key_tuple(intent.get("key"))
        system = key[1] if key is not None else "-"
        action = f"{intent.get('entry_action', '-')} {intent.get('quantity', 0)}"
        entry = f"entry {_fmt_float(intent.get('entry_stop_price'))}"
        stop = f"stop {_fmt_float(intent.get('protective_stop_price'))}"
        result = _record_status(record)
        result_suffix = "" if result == "dry_run" else f" | {result}"
        lines.append(
            f"    - {system:<4} {intent.get('local_symbol', '-'):<14} "
            f"{action:<7} {entry:<16} {stop:<15} "
            f"risk {_fmt_cash(intent.get('total_risk')):>12} "
            f"| {intent.get('exchange', '-')}{result_suffix}"
        )
    return lines


def _maintenance_lines(records: list[dict]) -> list[str]:
    rows = [
        record
        for record in records
        if not _is_bracket_intent(record.get("intent", {}))
    ]
    if not rows:
        return ["", "  Maintenance: none"]

    lines = ["", "  Maintenance actions:"]
    for record in rows:
        intent = record.get("intent", {})
        key = _key_tuple(intent.get("key") or intent.get("old_key"))
        system = key[1] if key is not None else "-"
        lines.append(
            f"    - {system} {_intent_contract(intent)}: "
            f"{_intent_action(intent)} | {_intent_details(intent, record)} "
            f"| {_record_status(record)}"
        )
    return lines


def _skipped_lines(skipped: list[dict]) -> list[str]:
    if not skipped:
        return ["", "  Skipped signals: none"]
    lines = ["", "  Skipped signals:"]
    for item in skipped:
        key = _key_tuple(item.get("key"))
        system = key[1] if key is not None else "-"
        lines.append(
            f"    - {system} {item.get('local_symbol', '-')} "
            f"({item.get('symbol', '-')}): {item.get('reason', '-')}"
        )
    return lines


def _alert_lines(alerts: list[dict]) -> list[str]:
    if not alerts:
        return ["", "  Alerts: none"]
    lines = ["", "  Alerts:"]
    for alert in alerts:
        action = alert.get("operator_action")
        message = alert.get("message", "")
        if action:
            message = f"{message} | action: {action}"
        lines.append(
            f"    - {alert.get('level', 'warning')} "
            f"{alert.get('code', '-')} {_fmt_key(alert.get('key'))}: {message}"
        )
    return lines


def _event_lines(events: list[ExecutionEvent]) -> list[str]:
    if not events:
        return []
    lines = ["", "  Execution events:"]
    for event in events:
        lines.append(
            f"    - {_value(event.status)} {event.intent} "
            f"order={event.order_id or '-'} key={_fmt_key(event.key)} "
            f"{event.message or ''}".rstrip()
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


def _bracket_order_type_label(records: list[dict]) -> str:
    order_types = {
        (
            record.get("intent", {}).get("entry_order_type"),
            record.get("intent", {}).get("protective_order_type"),
        )
        for record in records
    }
    if len(order_types) != 1:
        return ""
    entry_type, stop_type = next(iter(order_types))
    if not entry_type or not stop_type:
        return ""
    return f"; entry={entry_type}, stop={stop_type}"


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


def _fmt_cash(value: object, *, symbol: bool = True) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    amount = f"{number:,.2f}"
    if amount.endswith(".00"):
        amount = amount[:-3]
    prefix = "$" if symbol else ""
    return prefix + amount


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _record_status(record: dict) -> str:
    ids = _record_order_ids(record)
    status = _value(record.get("status", "-"))
    if ids:
        return f"{status} orders={ids}"
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


def _intent_label(class_name: str) -> str:
    labels = {
        "AlertIntent": "alerts",
        "CancelOrderIntent": "cancels",
        "ExitPositionIntent": "exits",
        "LastDayCloseoutIntent": "last-day exits",
        "ModifyOrderIntent": "modifies",
        "PlaceBracketIntent": "new brackets",
        "RollEntryIntent": "roll entries",
    }
    return labels.get(class_name, class_name)


def _is_info_message(error: BrokerError) -> bool:
    return _value(error.severity).lower() == "info"
