# IBKR Historical Refresh Plan

## Scope

This note covers only the IBKR historical data refresh path in:

- `src/quintet/contract_handler/historical_bars.py`
- `src/quintet/contract_handler/update_contracts.py`

Constraint: active contracts must continue to receive a full refresh on every run.

## Current Behavior

- Active contracts are always re-fetched with a full `1 Y` historical request.
- Expired contracts can be skipped if already cached.
- Requests are sent through one async `ibapi` client with a fixed in-flight cap.
- The caller also groups work into fixed 40-request batches.

Observed runtime from recent logs:

- 63 requests: about 72.5s
- 94 requests: about 169.7s
- 462 requests: about 917.9s

The main self-imposed delay is the batch barrier: later work waits for the slowest request in the current batch.

## Proposed Design

1. Keep the full-refresh rule for active contracts.
2. Replace fixed outer batches with one rolling request queue.
3. Keep a bounded in-flight cap, but launch the next request as soon as one finishes.
4. Split daily and hourly requests into separate lanes so a few large hourly pulls do not block many smaller daily pulls.
5. Add per-request timing, bar-count, and error logging.
6. Add request deadline, `cancelHistoricalData`, and bounded retry/backoff.
7. Make concurrency configurable and tune it from real runs instead of fixing it permanently at 45.
8. If this refresh is triggered by a user-facing API call, move the refresh off that request path and serve cached data first.

## Implementation Order

1. Add telemetry
2. Replace batch barriers with rolling scheduling
3. Split daily and hourly lanes
4. Add timeout, cancel, and retry
5. Tune concurrency
6. Decouple from synchronous API calls if needed

## Acceptance Criteria

- No change to the full-refresh behavior for active contracts
- No third-party libraries
- Lower default refresh runtime than current logs
- One slow or stuck contract does not stall unrelated contracts
- Logs identify the slowest symbols and request types directly

## References

- IBKR Campus TWS API docs: <https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/>
- IBKR Campus TWS API reference: <https://ibkrcampus.com/campus/ibkr-api-page/twsapi-ref/>
- IBKR Campus getting started: <https://ibkrcampus.com/campus/ibkr-api-page/getting-started/>
