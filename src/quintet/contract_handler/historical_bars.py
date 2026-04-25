"""Historical bars collector for futures contracts.

Built directly on the asynchronous EClient/EWrapper. Concurrency is bounded by
a semaphore matching IBKR's 50-simultaneous-open-historical-data-request cap;
beyond that there are no documented pacing limits for bar sizes >= 1 minute
(see https://interactivebrokers.github.io/tws-api/historical_limitations.html).

We allocate reqIds from a local thread-safe counter rather than via reqIds(-1)
(the order-id API), which is what causes "322 Duplicate ticker ID" errors
when reused for history.

No timeouts: every request waits on its own `historicalDataEnd` callback (or
an error short-circuit). If the connection drops, `connectionClosed` releases
every pending event so the caller wakes up cleanly.
"""

import itertools
import threading
from dataclasses import dataclass
from datetime import datetime

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

from quintet import config


# Error codes that mean "no data for this request" — signal completion with []
# rather than letting the caller hang. Same set as the prior sync-wrapper impl.
_EMPTY_RESPONSE_CODES = (162, 165, 166, 167, 200, 10314)

# Concurrency cap. IBKR's hard limit is 50 simultaneous open historical-data
# requests; staying a few below avoids racing the ceiling with internal
# bookkeeping requests.
_MAX_IN_FLIGHT = 45


@dataclass
class Bar:
    """OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class BarsRequest:
    """One historical-bars request slot for batch fetches."""
    local_symbol: str
    contract: Contract
    hourly: bool = False
    what_to_show: str = "TRADES"
    end_date_time: str = ""


def make_contract_by_id(con_id: int, exchange: str) -> Contract:
    """Create contract using conId (most reliable identification)."""
    c = Contract()
    c.conId = con_id
    c.exchange = exchange
    c.includeExpired = True
    return c


class HistoricalBars(EWrapper, EClient):
    """Concurrent historical-bars client built on the bare ibapi async API."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ):
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)

        self._connected = threading.Event()
        self._connection_dropped = False
        self._next_order_id: int | None = None

        # Per-reqId state. Populated when a request is launched.
        self._lock = threading.Lock()
        self._req_id_seq = itertools.count(start=1)
        self._bars: dict[int, list[Bar]] = {}
        self._events: dict[int, threading.Event] = {}

        # Bounded concurrency: at most _MAX_IN_FLIGHT requests open at once.
        # Each launch acquires a slot; each completion (end / error) releases
        # one. The release is guarded by `_event_done` so it fires exactly
        # once per request even if both `historicalDataEnd` and `error` arrive.
        self._slot = threading.Semaphore(_MAX_IN_FLIGHT)
        self._event_done: dict[int, bool] = {}

        host = host or config.HOST
        port = port or config.PORT
        client_id = client_id if client_id is not None else config.CLIENT_ID

        self.connect(host, port, client_id)
        self._reader_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._reader_thread.start()

        self._connected.wait()
        if self._connection_dropped:
            raise ConnectionError(f"Connection to {host}:{port} dropped before nextValidId")

    # -- internals -----------------------------------------------------

    def _run_loop(self) -> None:
        # EClient.run() raises when the socket is torn down by disconnect();
        # swallow that one expected exception so close() is clean.
        try:
            self.run()
        except (TypeError, OSError):
            pass

    def _next_req_id(self) -> int:
        with self._lock:
            return next(self._req_id_seq)

    def _signal_done(self, reqId: int) -> None:
        """Mark a request complete and release its concurrency slot exactly once."""
        with self._lock:
            if self._event_done.get(reqId):
                return
            self._event_done[reqId] = True
        ev = self._events.get(reqId)
        if ev is not None:
            ev.set()
        self._slot.release()

    @staticmethod
    def _convert_bar(bar) -> Bar:
        ts = (
            datetime.strptime(bar.date[:17], "%Y%m%d %H:%M:%S")
            if " " in bar.date
            else datetime.strptime(bar.date, "%Y%m%d")
        )
        return Bar(
            timestamp=ts,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=int(bar.volume),
        )

    # -- EWrapper callbacks --------------------------------------------

    def nextValidId(self, orderId: int) -> None:
        self._next_order_id = orderId
        self._connected.set()

    def connectionClosed(self) -> None:
        self._connection_dropped = True
        # Wake the connection waiter and every pending request so callers
        # never hang on a dead socket.
        self._connected.set()
        with self._lock:
            pending = [rid for rid, done in self._event_done.items() if not done]
        for rid in pending:
            self._signal_done(rid)

    def error(
        self,
        reqId: int,
        errorTime: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        # Connection-status notices, not real errors
        if errorCode in (2104, 2106, 2107, 2158):
            return
        print(f"IB error reqId={reqId} code={errorCode} {errorString}", flush=True)
        # Short-circuit known "no-data" codes so callers don't hang.
        if errorCode in _EMPTY_RESPONSE_CODES and reqId > 0:
            self._signal_done(reqId)

    def historicalData(self, reqId: int, bar) -> None:
        bucket = self._bars.get(reqId)
        if bucket is not None:
            bucket.append(self._convert_bar(bar))

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        self._signal_done(reqId)

    # -- public API -----------------------------------------------------

    def get_bars_for_many(self, requests: list[BarsRequest]) -> dict[str, list[Bar]]:
        """Fire all requests with a 45-in-flight cap and return bars by local_symbol.

        No timeouts. Each request waits on its own `historicalDataEnd` (or
        error short-circuit). `connectionClosed` releases every pending event
        so a dropped socket can't deadlock the caller.
        """
        # Allocate state for every request up front so callbacks arriving
        # before we've issued the next reqHistoricalData still find their
        # bucket.
        slots: list[tuple[int, BarsRequest]] = []
        for req in requests:
            rid = self._next_req_id()
            self._bars[rid] = []
            self._events[rid] = threading.Event()
            self._event_done[rid] = False
            slots.append((rid, req))

        # Fire each request, blocking on the semaphore so we never have
        # more than _MAX_IN_FLIGHT requests open at IBKR.
        for rid, req in slots:
            self._slot.acquire()
            bar_size = "1 hour" if req.hourly else "1 day"
            self.reqHistoricalData(
                rid,
                req.contract,
                req.end_date_time,
                "1 Y",
                bar_size,
                req.what_to_show,
                0,        # useRTH = False (matches prior behaviour)
                1,        # formatDate = 1 (yyyymmdd / yyyymmdd hh:mm:ss)
                False,    # keepUpToDate
                [],       # chartOptions
            )

        # Wait for every request to complete. No timeout — we trust IBKR
        # to always end with either historicalDataEnd or an error code, and
        # connectionClosed releases everything if the socket dies.
        for rid, _req in slots:
            self._events[rid].wait()

        out: dict[str, list[Bar]] = {}
        for rid, req in slots:
            out[req.local_symbol] = self._bars.pop(rid, [])
            self._events.pop(rid, None)
            self._event_done.pop(rid, None)
        return out

    def get_bars_for_period(
        self,
        contract: Contract,
        hourly: bool = False,
        what_to_show: str = "TRADES",
        end_date_time: str = "",
    ) -> list[Bar]:
        """Fetch 1 year of bars (hourly or daily) for a single contract.

        end_date_time: YYYYMMDD or YYYYMMDD HH:MM:SS, or "" for now.
        """
        local = contract.localSymbol or f"req_{id(contract)}"
        result = self.get_bars_for_many([
            BarsRequest(
                local_symbol=local,
                contract=contract,
                hourly=hourly,
                what_to_show=what_to_show,
                end_date_time=end_date_time,
            )
        ])
        return result.get(local, [])

    def close(self) -> None:
        """Disconnect from TWS/Gateway."""
        self.disconnect()
        if self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2)
