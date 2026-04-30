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

## Remaining Slices

2. **Last-day maintenance exits**
   - Generate `ExitPositionIntent` for held positions at the configured last-day rule.
   - Keep this in maintenance planning, not signal scanning.
   - Add pure planner tests with fabricated broker state.
   - Commit when complete.

3. **Roll handling for equity flows**
   - Keep roll planning separate from normal entry scanning.
   - Start with planner/report output before adding live execution.
   - Add tests for roll-eligible vs. not-yet-eligible positions.
   - Commit when complete.

4. **Execution reporting cleanup**
   - Report submitted, cancel-requested, modified, reported-only, alerts, and threw counts separately.
   - Keep JSON report and CLI summary consistent.
   - Add serialization/report tests.
   - Commit when complete.

5. **Dashboard/report viewer**
   - Surface latest trade plan and execution report in the dashboard.
   - Make operator actions clear for alerts and reported-only intents.
   - Avoid changing scanner/signal behavior.
   - Commit when complete.

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
