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

- Live exit execution has unit coverage only. A true paper Gateway test requires deliberately opening and closing a filled position, which is possible but should be reviewed before making it part of the routine suite.
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

## Remaining Slices

9. **Live roll executor wiring**
   - Teach `IbkrExecutor` to submit the complete close-and-roll bundle instead of reporting it only.
   - Sequence roll placement as one broker operation: cancel existing stop, submit replacement stop + RTH market exit OCA pair, then submit the RTH market roll-entry parent and protective child stop when a roll entry qualifies.
   - Preserve fail-fast behavior: if order construction or placement throws, record `roll_threw` and continue reporting the failure; do not silently fallback.
   - Add execution-report status/count coverage for roll-submitted and roll-threw outcomes.
   - Add executor tests proving the full roll bundle places the expected old-contract OCA orders and new-contract bracket orders.
   - Commit when complete.

10. **Live roll planning integration check**
   - Verify maintenance emits a single close-and-roll bundle on `today >= last_day`, not disconnected old-exit and new-entry intents.
   - Verify the bundle includes the current protective stop details from reconciled broker state.
   - Verify roll-enabled equity systems can roll, while commodity systems remain non-roll.
   - Verify missing candidate, same-contract candidate, low RSpos, missing RSpos, and missing stop still alert without order placement.
   - Commit when complete.

11. **Paper Gateway roll validation**
   - Start only from a clean paper state unless explicitly testing manual/outside state.
   - Create or simulate one old-contract position plus protective stop in a controlled configured equity future.
   - Run a trade plan containing the close-and-roll bundle.
   - Confirm the old protective stop remains protective during ETH through the replacement-stop OCA order, the old RTH market exit is paired with that replacement stop, and the new RTH market entry has an attached protective stop.
   - Cleanup must leave `positions: 0` and `open orders: 0`.
   - Record the tested contract, order ids, and cleanup result in this todo file.
   - Commit when complete.

12. **Operator/report polish for live rolls**
   - Show live roll submissions separately in the CLI/dashboard counts.
   - Include old contract, new contract, quantity, RSpos, threshold, and stop price in the execution report.
   - Keep reported-only roll alerts visible for non-executed roll cases.
   - Commit when complete.

13. **Final full verification**
   - Run the full local test suite.
   - Run the forbidden hard-code/timeout grep.
   - Run a final configured Gateway state check.
   - Confirm unrelated dirty files were not included in commits.
   - Commit any final documentation updates.
