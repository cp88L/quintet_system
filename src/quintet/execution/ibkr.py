"""Live IBKR executor for broker-neutral trade plans."""

from __future__ import annotations

from datetime import datetime

from quintet.broker.ibkr.orders import build_bracket_order_requests
from quintet.broker.ibkr.state import IbkrStateClient
from quintet.execution.models import (
    AlertIntent,
    CancelOrderIntent,
    ExecutionEvent,
    ExecutionReport,
    ExecutionStatus,
    PlaceBracketIntent,
)
from quintet.execution.serialize import to_plain
from quintet.trading.models import TradePlan


class IbkrExecutor:
    """Submit supported intents to IBKR without waiting for acknowledgments."""

    mode = "live"

    def execute(self, plan: TradePlan) -> ExecutionReport:
        """Execute a trade plan against the configured paper Gateway."""
        client = IbkrStateClient()
        client.connect_and_run()
        try:
            return self.execute_connected(plan, client)
        finally:
            client.disconnect_and_stop()

    def execute_connected(
        self,
        plan: TradePlan,
        client: IbkrStateClient,
    ) -> ExecutionReport:
        submitted: list[dict] = []
        alerts: list[dict] = []
        events: list[ExecutionEvent] = []

        for intent in plan.intents:
            if isinstance(intent, AlertIntent):
                alerts.append(to_plain(intent))
                continue
            if isinstance(intent, CancelOrderIntent):
                self._cancel_order(intent, client, submitted, events)
                continue
            if not isinstance(intent, PlaceBracketIntent):
                events.append(
                    ExecutionEvent(
                        status=ExecutionStatus.REPORTED,
                        intent=intent.__class__.__name__,
                        key=getattr(intent, "key", None),
                        message="intent type not wired for live execution yet",
                    )
                )
                continue

            try:
                order_ids = self._place_bracket(intent, client, events)
            except Exception as exc:
                events.append(
                    ExecutionEvent(
                        status=ExecutionStatus.PLACE_THREW,
                        intent=intent.__class__.__name__,
                        key=intent.key,
                        message=str(exc),
                    )
                )
                continue

            submitted.append(
                {
                    "status": ExecutionStatus.SUBMITTED.value,
                    "order_ids": order_ids,
                    "intent": to_plain(intent),
                }
            )

        open_orders_after = [to_plain(o) for o in client.get_open_orders()]
        return ExecutionReport(
            generated_at=datetime.now(),
            mode=self.mode,
            submitted=submitted,
            skipped=plan.skipped,
            alerts=alerts,
            open_orders_after=open_orders_after,
            events=events,
        )

    def _cancel_order(
        self,
        intent: CancelOrderIntent,
        client: IbkrStateClient,
        submitted: list[dict],
        events: list[ExecutionEvent],
    ) -> None:
        try:
            client.cancel_order(intent.order_id)
        except Exception as exc:
            events.append(
                ExecutionEvent(
                    status=ExecutionStatus.CANCEL_THREW,
                    intent=intent.__class__.__name__,
                    order_id=intent.order_id,
                    key=intent.key,
                    message=str(exc),
                )
            )
            return

        submitted.append(
            {
                "status": ExecutionStatus.CANCEL_REQUESTED.value,
                "order_id": intent.order_id,
                "intent": to_plain(intent),
            }
        )
        events.append(
            ExecutionEvent(
                status=ExecutionStatus.CANCEL_REQUESTED,
                intent=intent.__class__.__name__,
                order_id=intent.order_id,
                key=intent.key,
            )
        )

    def _place_bracket(
        self,
        intent: PlaceBracketIntent,
        client: IbkrStateClient,
        events: list[ExecutionEvent],
    ) -> list[int]:
        entry_order_id = client.get_next_order_id()
        stop_order_id = client.get_next_order_id()
        requests = build_bracket_order_requests(
            intent,
            entry_order_id=entry_order_id,
            stop_order_id=stop_order_id,
        )
        for request in requests:
            client.place_order(request.order_id, request.contract, request.order)
            events.append(
                ExecutionEvent(
                    status=ExecutionStatus.SUBMITTED,
                    intent=intent.__class__.__name__,
                    order_id=request.order_id,
                    key=intent.key,
                )
            )
        return [entry_order_id, stop_order_id]
