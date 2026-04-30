"""IBKR state collection and order submission for the daily trade flow."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from ibapi.client import EClient
from ibapi.common import OrderId
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper

from quintet import config
from quintet.broker.ibkr.mapper import (
    map_account_summary,
    map_open_order,
    map_position,
)
from quintet.broker.models import (
    AccountState,
    BrokerError,
    BrokerErrorSeverity,
    BrokerOrder,
    BrokerPosition,
    BrokerState,
)


class IbkrStateClient(EWrapper, EClient):
    """Small IBKR client for account, position, open-order, and order state."""

    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self._connected = threading.Event()
        self._positions_end = threading.Event()
        self._orders_end = threading.Event()
        self._account_summary_end = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._connection_closed = False
        self._next_order_id: int | None = None

        self._positions: list[BrokerPosition] = []
        self._open_orders: dict[int, BrokerOrder] = {}
        self._account_summary_rows: list[dict[str, str]] = []
        self._errors: list[BrokerError] = []

    def connect_and_run(self) -> None:
        """Connect and start the IBKR reader thread."""
        _require_client_zero()
        try:
            self.connect(config.HOST, config.PORT, config.CLIENT_ID)
        except Exception as exc:
            raise ConnectionError(
                f"Failed to open IBKR socket at {config.HOST}:{config.PORT}"
            ) from exc
        if not self.isConnected():
            raise ConnectionError(
                f"Failed to connect to IBKR at {config.HOST}:{config.PORT}"
            )
        self._reader_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._reader_thread.start()
        self._connected.wait()
        self._raise_if_closed("connect")
        if config.CLIENT_ID == 0:
            self.reqAutoOpenOrders(True)

    def disconnect_and_stop(self) -> None:
        """Disconnect from IBKR."""
        self.disconnect()

    def _run_loop(self) -> None:
        try:
            self.run()
        except (TypeError, OSError):
            pass

    def nextValidId(self, orderId: OrderId) -> None:
        self._next_order_id = int(orderId)
        self._connected.set()

    def connectionClosed(self) -> None:
        self._connection_closed = True
        self._connected.set()
        self._positions_end.set()
        self._orders_end.set()
        self._account_summary_end.set()

    def error(
        self,
        reqId: int,
        errorTime: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        severity = (
            BrokerErrorSeverity.INFO
            if errorCode in {2104, 2106, 2107, 2158}
            else BrokerErrorSeverity.WARNING
            if errorCode >= 2100
            else BrokerErrorSeverity.ERROR
        )
        with self._lock:
            self._errors.append(
                BrokerError(
                    request_id=reqId,
                    code=errorCode,
                    message=errorString,
                    timestamp=datetime.now(tz=timezone.utc),
                    severity=severity,
                )
            )

    def position(self, account: str, contract: Contract, pos, avgCost: float) -> None:
        if float(pos) == 0:
            return
        with self._lock:
            self._positions.append(map_position(account, contract, pos, avgCost))

    def positionEnd(self) -> None:
        self._positions_end.set()

    def openOrder(
        self,
        orderId: OrderId,
        contract: Contract,
        order: Order,
        orderState: OrderState,
    ) -> None:
        with self._lock:
            self._open_orders[int(orderId)] = map_open_order(
                int(orderId),
                contract,
                order,
                orderState,
            )

    def openOrderEnd(self) -> None:
        self._orders_end.set()

    def accountSummary(
        self,
        reqId: int,
        account: str,
        tag: str,
        value: str,
        currency: str,
    ) -> None:
        with self._lock:
            self._account_summary_rows.append(
                {
                    "account": account,
                    "tag": tag,
                    "value": value,
                    "currency": currency,
                }
            )

    def accountSummaryEnd(self, reqId: int) -> None:
        self._account_summary_end.set()

    def get_positions(self) -> list[BrokerPosition]:
        with self._lock:
            self._positions.clear()
        self._positions_end.clear()
        self.reqPositions()
        self._positions_end.wait()
        self._raise_if_closed("positions")
        return self.positions_snapshot()

    def get_open_orders(self) -> list[BrokerOrder]:
        with self._lock:
            self._open_orders.clear()
        self._orders_end.clear()
        self.reqAllOpenOrders()
        self._orders_end.wait()
        self._raise_if_closed("open orders")
        return self.open_orders_snapshot()

    def get_account_state(self) -> AccountState:
        req_id = 7001
        with self._lock:
            self._account_summary_rows.clear()
        self._account_summary_end.clear()
        self.reqAccountSummary(req_id, "All", "NetLiquidation,BuyingPower")
        self._account_summary_end.wait()
        self._raise_if_closed("account summary")
        self.cancelAccountSummary(req_id)
        with self._lock:
            rows = list(self._account_summary_rows)
        return map_account_summary(rows)

    def collect_state(self) -> BrokerState:
        """Collect current account, position, and open-order state."""
        account = self.get_account_state()
        positions = self.get_positions()
        open_orders = self.get_open_orders()
        errors = self.errors_snapshot()
        return BrokerState(
            collected_at=datetime.now(tz=timezone.utc),
            account=account,
            positions=positions,
            open_orders=open_orders,
            recent_errors=errors,
        )

    def positions_snapshot(self) -> list[BrokerPosition]:
        with self._lock:
            return list(self._positions)

    def open_orders_snapshot(self) -> list[BrokerOrder]:
        with self._lock:
            return list(self._open_orders.values())

    def errors_snapshot(self) -> list[BrokerError]:
        with self._lock:
            return list(self._errors)

    def get_next_order_id(self) -> int:
        """Return and reserve the next IBKR order id."""
        with self._lock:
            if self._next_order_id is None:
                raise RuntimeError("IBKR did not provide nextValidId")
            order_id = self._next_order_id
            self._next_order_id += 1
            return order_id

    def place_order(self, order_id: int, contract: Contract, order: Order) -> None:
        """Submit an order to IBKR."""
        self.placeOrder(order_id, contract, order)

    def cancel_order(self, order_id: int) -> None:
        """Cancel an order by id."""
        from ibapi.order_cancel import OrderCancel

        self.cancelOrder(order_id, OrderCancel())

    def _raise_if_closed(self, operation: str) -> None:
        if self._connection_closed:
            raise ConnectionError(f"IBKR connection closed during {operation}")


def _require_client_zero() -> None:
    """Fail fast if broker-state visibility would exclude manual orders."""
    if config.CLIENT_ID != 0:
        raise ValueError(
            "Quintet broker-state collection requires config.CLIENT_ID = 0 "
            "so manual TWS/Gateway trades and orders are included."
        )


class IbkrBrokerGateway:
    """Read-only gateway that rebuilds broker state from IBKR each run."""

    def collect_state(self) -> BrokerState:
        """Collect current account, position, and open-order state from IBKR."""
        client = IbkrStateClient()
        try:
            client.connect_and_run()
            return client.collect_state()
        finally:
            client.disconnect_and_stop()
