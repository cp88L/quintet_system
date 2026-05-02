"""IBKR state collection and order submission for the daily trade flow."""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone

from ibapi.client import EClient
from ibapi.common import OrderId
from ibapi.contract import Contract
from ibapi.execution import ExecutionFilter
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper

from quintet import config
from quintet.broker.ibkr.calendar import parse_next_rth_day
from quintet.broker.ibkr.mapper import (
    map_account_summary,
    map_open_order,
    map_position,
)
from quintet.broker.models import (
    AccountState,
    BrokerFill,
    BrokerError,
    BrokerErrorSeverity,
    BrokerOrder,
    BrokerPosition,
    BrokerState,
    ContractMeta,
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
        self._contract_details_end = threading.Event()
        self._executions_end = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._connection_closed = False
        self._next_order_id: int | None = None
        self._contract_details_req_id = 8000

        self._positions: list[BrokerPosition] = []
        self._open_orders: dict[int, BrokerOrder] = {}
        self._account_summary_rows: list[dict[str, str]] = []
        self._contract_details: dict[int, object] = {}
        self._executions: dict[str, BrokerFill] = {}
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
        self._contract_details_end.set()
        self._executions_end.set()

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

    def contractDetails(self, reqId: int, contractDetails) -> None:
        with self._lock:
            self._contract_details[int(reqId)] = contractDetails

    def contractDetailsEnd(self, reqId: int) -> None:
        self._contract_details_end.set()

    def execDetails(self, reqId: int, contract: Contract, execution) -> None:
        fill = BrokerFill(
            exec_id=str(getattr(execution, "execId", "") or ""),
            order_id=int(getattr(execution, "orderId", 0) or 0),
            con_id=int(getattr(contract, "conId", 0) or 0),
            symbol=str(getattr(contract, "symbol", "") or ""),
            local_symbol=str(getattr(contract, "localSymbol", "") or ""),
            side=str(getattr(execution, "side", "") or ""),
            quantity=int(float(getattr(execution, "shares", 0) or 0)),
            price=float(getattr(execution, "price", 0.0) or 0.0),
            time=str(getattr(execution, "time", "") or ""),
            order_ref=str(getattr(execution, "orderRef", "") or "") or None,
        )
        if not fill.exec_id:
            return
        with self._lock:
            self._executions[fill.exec_id] = fill

    def execDetailsEnd(self, reqId: int) -> None:
        self._executions_end.set()

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
        details_by_con_id = self.get_contract_details_for_con_ids(
            {p.con_id for p in positions}
        )
        next_rth_days = {
            con_id: next_day
            for con_id, details in details_by_con_id.items()
            if (next_day := _next_rth_day_from_details(details)) is not None
        }
        contract_meta = {
            con_id: meta
            for con_id, details in details_by_con_id.items()
            if (meta := _contract_meta_from_details(con_id, details)) is not None
        }
        recent_fills = self.get_recent_fills()
        errors = self.errors_snapshot()
        return BrokerState(
            collected_at=datetime.now(tz=timezone.utc),
            account=account,
            positions=positions,
            open_orders=open_orders,
            recent_fills=recent_fills,
            next_rth_days=next_rth_days,
            contract_meta=contract_meta,
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

    def get_next_rth_days(self, con_ids: set[int]) -> dict[int, date]:
        """Fetch each current position contract's next RTH session date."""
        next_days: dict[int, date] = {}
        for con_id in sorted(con_ids):
            next_day = self.get_next_rth_day(con_id)
            if next_day is not None:
                next_days[con_id] = next_day
        return next_days

    def get_next_rth_day(self, con_id: int) -> date | None:
        """Fetch and parse the next RTH session date for one contract."""
        details = self.get_contract_details(con_id)
        if details is None:
            return None
        return _next_rth_day_from_details(details)

    def get_contract_details_for_con_ids(self, con_ids: set[int]) -> dict[int, object]:
        """Fetch raw IBKR contract details for current position contracts."""
        details_by_con_id: dict[int, object] = {}
        for con_id in sorted(con_ids):
            details = self.get_contract_details(con_id)
            if details is not None:
                details_by_con_id[con_id] = details
        return details_by_con_id

    def get_contract_details(self, con_id: int) -> object | None:
        """Fetch raw IBKR contract details for one contract id."""
        req_id = self._next_contract_details_req_id()
        contract = Contract()
        contract.conId = con_id

        self._contract_details_end.clear()
        with self._lock:
            self._contract_details.pop(req_id, None)
        self.reqContractDetails(req_id, contract)
        self._contract_details_end.wait()
        self._raise_if_closed("contract details")

        with self._lock:
            details = self._contract_details.pop(req_id, None)
        return details

    def get_recent_fills(
        self,
        *,
        lookback_hours: int = config.EXECUTION_LOOKBACK_HOURS,
        timeout: float = 10.0,
    ) -> list[BrokerFill]:
        """Fetch recent execution fills from IBKR for entry-date display."""
        req_id = 9002
        exec_filter = ExecutionFilter()
        lookback_start = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        exec_filter.time = lookback_start.strftime("%Y%m%d-%H:%M:%S")

        with self._lock:
            self._executions.clear()
        self._executions_end.clear()
        self.reqExecutions(req_id, exec_filter)
        if not self._executions_end.wait(timeout):
            return []
        self._raise_if_closed("executions")
        with self._lock:
            return list(self._executions.values())

    def _next_contract_details_req_id(self) -> int:
        with self._lock:
            req_id = self._contract_details_req_id
            self._contract_details_req_id += 1
            return req_id

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


def _next_rth_day_from_details(details) -> date | None:
    return parse_next_rth_day(getattr(details, "liquidHours", "") or "")


def _contract_meta_from_details(con_id: int, details) -> ContractMeta | None:
    contract = getattr(details, "contract", None)
    if contract is None:
        return None
    last_trade_date = _parse_ibkr_contract_date(
        getattr(contract, "lastTradeDateOrContractMonth", "") or ""
    )
    return ContractMeta(
        con_id=con_id,
        symbol=str(getattr(contract, "symbol", "") or ""),
        local_symbol=str(getattr(contract, "localSymbol", "") or ""),
        exchange=str(getattr(contract, "exchange", "") or ""),
        currency=str(getattr(contract, "currency", "") or ""),
        multiplier=_optional_float(getattr(contract, "multiplier", None)) or 1.0,
        min_tick=_optional_float(getattr(details, "minTick", None)) or 0.0,
        price_magnifier=int(
            _optional_float(getattr(details, "priceMagnifier", None)) or 1
        ),
        last_trade_date=last_trade_date,
        last_day=None,
    )


def _parse_ibkr_contract_date(value: str) -> date | None:
    value = str(value or "")
    if len(value) < 8:
        return None
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number < 1e300 else None


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
