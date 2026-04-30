# Trade Flow Implementation Todo

Rules for every slice:

- Do not change signal/business logic unless explicitly requested.
- Keep IBKR adapter code separate from trading/business logic.
- Use configured IBKR values; never hard-code the paper port.
- No fallbacks or timeout knobs in the broker-state path.
- Test each slice as it is implemented, including paper Gateway coverage when relevant.
- Clean up any paper orders created during tests.
- Commit at the end of each completed slice.
- Continue through the list without stopping for non-blocking decisions while the user is away.
- When a choice is unclear, make the most conservative implementation decision that preserves existing signal/business behavior, document it, and keep moving.
- Compile deferred questions in the section below for review after all slices are complete.

## Deferred Questions For Review

Add questions here instead of stopping unless continuing would risk orders, account safety, or signal/business-rule drift.

- Live exit execution has ad hoc paper Gateway coverage from cleanup flows, but no routine live test. Decide later whether live order tests should become a maintained manual checklist or remain ad hoc only.
- 2026-04-30 ad hoc paper validation opened one ES position and confirmed a protective stop could trigger and return the account to flat. This did not add a routine test.

## Completed Slices

1. **Live exit execution**
   - Wired `ExitPositionIntent` into `IbkrExecutor`.
   - Added IBKR market exit order building from broker-neutral intent data.
   - Added unit tests for order building and executor dispatch.
   - Deferred filled-position paper Gateway coverage for review.

2. **Last-day maintenance exits**
   - Generate `ExitPositionIntent` for reconciled positions on/after known contract `last_day`.
   - Alert instead of guessing when last-day metadata is missing.
   - Keep exit planning in maintenance, separate from signal scanning.
   - Commit when complete.

3. **Roll handling for equity flows**
   - Add planner/report-only `RollEntryIntent`.
   - Generate roll-entry reports only for roll-enabled systems when current-contract `RSpos` meets the configured threshold.
   - Report missing, not-yet-advanced, below-threshold, or missing-stop roll state as alerts.
   - Keep live roll execution deferred.

4. **Execution reporting cleanup**
   - Add computed execution counts for submitted, cancel-requested, modified, reported-only, alerts, threw, dry-run, and skipped outcomes.
   - Print the same count fields in the CLI summary that are written to `latest_execution_report.json`.
   - Add serialization/report tests.

5. **Dashboard/report viewer**
   - Add a `/trade` dashboard page for latest trade plan and execution report JSON.
   - Surface counts, alerts, reported-only roll entries, submitted/requested records, and skipped candidates.
   - Add operator-action text for alerts and deferred roll entries.
   - Add dashboard registration and report-loader tests.

6. **End-to-end broker-state scenario tests**
   - Add broker-state-to-plan tests for stale entry cancel.
   - Add broker-state-to-plan tests for entry modify.
   - Add broker-state-to-plan tests for position stop modify.
   - Add broker-state-to-plan tests for missing stop alerts.
   - Add broker-state-to-plan tests for manual/outside-system order alerts.

7. **Manual/outside-system trade hardening**
   - Keep handling report-only.
   - Add `operator_action` to alert reports.
   - Improve manual/outside-system alert messages with relevant broker details.
   - Add tests for client-0 manual-order visibility assumptions.

8. **Live roll order builder**
   - Added broker-neutral last-day closeout intent data and protective-stop snapshot.
   - Added old-contract replacement-stop OCA order builder using Quartet's closeout mechanics.
   - Added new-contract RTH market roll parent and ETH protective stop child builder.
   - Added unit tests for long/short closeout OCA orders and long roll-entry bracket orders.

9. **Live roll executor wiring**
   - Wired `IbkrExecutor` to submit the complete close-and-roll bundle.
   - Cancel existing stop, submit replacement stop + RTH market exit OCA pair, then submit the RTH market roll-entry parent and protective child stop when present.
   - Added `roll_submitted` / `roll_threw` report statuses and roll-submitted counts.
   - Added executor tests proving the expected old-contract OCA orders and new-contract bracket orders are placed.

10. **Live roll planning integration check**
   - Maintenance now emits a single `LastDayCloseoutIntent` bundle when the broker calendar says `next_rth_day >= last_day`.
   - The bundle includes current protective stop id, type, prices, and deterministic OCA group.
   - Roll-enabled equity systems attach qualifying next-contract roll entries to that bundle.
   - Commodity systems keep closeout-only behavior.
   - Missing candidate, same-contract candidate, low RSpos, missing RSpos, and missing stop keep the closeout and emit alerts instead of roll entry.

11. **Paper Gateway roll validation**
   - 2026-04-30 configured paper Gateway validation used ES current contract `ESM6` (`conId=649180678`) and upcoming contract `ESU6` (`conId=649180671`).
   - Started from clean paper state: `positions=0`, `open_orders=0`.
   - Opened old-contract long position with order `188`, then placed old protective `SELL STP LMT` order `189`.
   - Executed one `LastDayCloseoutIntent` bundle through `IbkrExecutor`.
   - Submitted replacement stop order `190`, RTH market closeout order `191`, RTH roll-entry parent order `192`, and new protective stop child order `193`.
   - Confirmed old position was flat, new position was long one `ESU6`, and order `193` remained open as the new protective stop.
   - Cleanup cancelled order `193`, flattened `ESU6` through live exit execution, and ended with `positions=0`, `open_orders=0`.

12. **Operator/report polish for live rolls**
   - CLI summary now prints `roll submitted` separately from general submitted counts.
   - Dashboard count cards now include `roll submitted`.
   - Live and dry-run execution records now include `roll_summary` with old contract, new contract, quantity, RSpos, threshold, and protective stop price.
   - Dashboard submitted rows now render closeout/roll order ids and roll summary details.
   - Reported-only roll rows no longer say live roll placement is deferred.

13. **Final full verification**
   - Ran the full local test suite: `python -m unittest` passed `57` tests.
   - Ran the scoped forbidden hard-code/timeout grep across trade-flow, broker, execution, run, and tests paths; no matches outside the real config file.
   - Ran a final configured Gateway state check through `IbkrBrokerGateway` using `127.0.0.1:4002` and `client_id=0`.
   - Gateway ended clean: `positions=0`, `open_orders=0`.
   - Broker messages were informational IBKR farm/status messages only.
   - Confirmed unrelated dirty files were not staged or committed.

14. **Calendar-driven last-day roll trigger**
   - Copied Quartet's IBKR `liquidHours` calendar concept into the Quintet broker adapter.
   - `BrokerState` now carries broker-neutral `next_rth_days` keyed by `con_id`.
   - Maintenance now compares `next_rth_day >= last_day`, so the EOD/break run before `last_day` can stage the RTH-open closeout and optional roll.
   - Missing broker calendar data produces a report-only `missing_next_rth_day` alert instead of guessing from the wall-clock date.
   - Read-only configured Gateway check confirmed active `ESM6` calendar parsing through `127.0.0.1:4002`, `client_id=0`.
   - Full local suite passed `60` tests.

## Remaining Slices

- None.
