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

## Remaining Slices

6. **End-to-end broker-state scenario tests**
   - Cover stale entry cancel.
   - Cover entry modify.
   - Cover position stop modify.
   - Cover missing stop alert.
   - Cover manual/outside-system order alert.
   - Commit when complete.

7. **Manual/outside-system trade hardening**
   - Keep handling simple and report-only unless explicitly approved.
   - Improve alert messages and report fields for operator action.
   - Add tests around client-0 visibility assumptions.
   - Commit when complete.
