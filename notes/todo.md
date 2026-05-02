# Quintet — open work as of 2026-04-30

## Tomorrow's first task: roll-target indicator scope

**The problem.** The trade-flow spec's roll bundle requires three numbers from
the *next* contract whenever a held position approaches `last_day`:

- `Sup_N` (long) / `Res_N` (short) — for the new bracket's protective stop
- `RSpos_N` — for the side-aware roll-in filter (long: `>= ROLL_RSPOS_MIN[s]`,
  short: `<= ROLL_RSPOS_MAX[s]`)

These come from the new contract's processed parquet under
`processed/{system}/{symbol}/{next_local_symbol}.parquet`.

**Why the current pipeline doesn't supply them.** `quintet/run/__main__.py`'s
`_build_active_locals` scopes the daily fetch + indicators + predictions
stages to contracts whose scan window contains today
(`start_scan <= today <= last_day`). On `last_day`, the next contract's
`start_scan` is typically *after* today — its scan hasn't begun, so it isn't
in `active_locals`. The fetch / indicators / predictions stages skip it,
and its parquet is either missing or stale by the time the maintenance plan
needs to read `RSpos_N` / `Sup_N` / `Res_N` from it.

CS4 and C4 have `ROLL_ENABLED = False` so they don't expose this today.
E4 / E7 / E13 will hit it the first time a held position reaches its
`last_day`.

**Why the quick fix was rejected.** Auto-extending `active_locals` from
`maintain.py` (or its data-flow equivalent) would solve the data availability
but mixes scope-control logic into the maintenance planner, and ties the
fetch policy to the roll horizon in a way that's hard to reason about
across other use cases (e.g., dashboard precomputation, backfill).

**Notes for the proper fix (to be designed):**

- The data pipeline upstream uses `Active_Days` per bar (`+1` active scan,
  `-1` rollover, etc.). Quintet's contract registry has discrete scan
  window dates per contract; there's no analog of `Active_Days` on the
  bar-level data. Worth deciding whether the fix lives in the registry
  (overlap scan windows so the next contract's scan begins before the
  prior contract's `last_day`), or in the fetch/process scope rule
  (always include the *next* contract per active product), or somewhere
  else.
- Whatever the fix, it should be predictable enough that it doesn't
  surprise the operator: "today's run also processed contract X" should
  be obvious from the inputs.
- Backtest doesn't have this problem because it post-processes a
  full-history pickle — every contract's bars are pre-computed across
  the entire universe. Quintet's incremental approach (only process
  what's active today) is the source of the gap.
- The spec (§3 "Open issue: roll-target indicator scope") flags this
  but does not commit to a solution.
- `ROLL_LOOKAHEAD_DAYS = 5` was added to `config.py` for the reporting
  countdown (held position warnings in the run report). It is **not**
  a data-scope solution; do not repurpose it.

**Out of this work, also revisit:**

- Whether the contract registry's `start_scan` of contract N+1 should
  overlap with `last_day` of contract N for systems with `ROLL_ENABLED`.
  If yes, this is a registry-generation-time fix, and the daily scope
  rule wouldn't need to change.

## Bugs identified, not fixed

1. **data_pipeline `TARGET_MARGIN = 0.02` is a regression.** Commit
   `e3085a8` "add short side" (2026-03-14) flipped it from 0.10 → 0.02
   inside a giant unrelated commit. The optimized backtest run on
   `c654249` → `ecc3be0` (2025-12-27 → 2026-02-19) used 0.10. Quintet
   currently matches the regressed 0.02 for parity. To restore the
   optimized regime: revert `data_pipeline_package/config.py:23` to
   0.10, regenerate every entries parquet + processed pickle, retrain
   XGBoost models, re-derive `PRECISION` per system, then mirror the
   same in quintet's `config.py`.
2. **Stale `_clusters.parquet` files were deleted earlier.**
   `make_predictions/clusters.py` does not write them; today's run
   produces only in-memory cluster output. If a downstream consumer
   ever expected the file, that's a gap.

## Next steps after the roll-scope fix (priority order)

1. Phase 1 of the trade-flow spec: dry-run scaffolding —
   broker-neutral dataclasses (`BrokerState`, `ReconciledTradeState`,
   `RiskState`, `TradePlan`, `ExecutionReport`), a `DryRunExecutor`
   that consumes a fabricated `BrokerState`, the daily-flow
   orchestrator wiring signal stages → trade stages in memory.
2. Phase 2: minimal IBKR broker adapter (`broker/ibkr/`) supporting
   `collect_broker_state()` only — no order placement.
3. Phase 3: maintenance planning (last-day exit + conditional roll
   bundle, orphaned-stop cleanup, missing-stop alerts). Depends on
   the roll-target indicator scope being resolved.
4. Phase 4: trade-plan planning (side-aware brackets, pooled-equity
   sizing, tick-rounded modify trigger, skip reasons, stop-update
   intents).
5. Phase 5: live execution (fire-and-forget, async callback drain,
   replace-stop OCA pattern per
   `quartet/place_orders/test_order_tracking.py:870-910`).

## Decisions pending

- **Coordinate-revert TARGET_MARGIN to 0.10?** Big change (every
  backtest pickle, every model, all `PRECISION` values). Worth it if
  0.10 was the optimized regime.
- **Recalibrate `PRECISION` targets?** Some systems can produce NaN
  tau when the rolling pool can't meet the Wilson lower-bound target.
  Either accept "no signal for that system today" or retrain.
- **`LIMIT_OFFSET = 0.000`** — currently no buffer above resistance /
  below support for stop-limit entries. The backtest's
  `buy_on_stop_price` / `sell_on_stop_price` assume a plain STP fill
  at the open price on gap-up days, so live STP LMT with offset 0
  will miss those entries (Decision #4 in the spec accepts this for
  v1; revisit if commodity gap rejections accumulate).

## Where to look on resume

- `docs/trade-flow-architecture-spec.md` — the canonical architecture
  spec; §3 "Open issue: roll-target indicator scope" flags tomorrow's
  task. Stage 3/Stage 5 split, side-aware roll bundle, fire-and-forget
  execution, three-skip-reason taxonomy, replace-stop OCA pattern all
  decided.
- `docs/backtest-improvements.md` — running log of live↔backtest
  divergences (SB/W §1, SR3 §2).
- `notes/cluster_missing_data.md` — known cluster-pool behavior on
  missing days.
- `quintet_storage/tools/regen_product_scan_windows.py` — surgical
  scan-window regen helper. Likely relevant if the proper fix for
  the roll-scope issue lives in registry generation.
- `data/processed/{system}/_lookback/*.parquet` — 60-bar tau pools.
- `data/processed/{system}/_tau.json` — latest tau snapshots.
- `data/processed/_funnel.json` — daily funnel snapshot consumed by
  the dashboard. `PositionStage` removal per the spec will affect
  the `position_pass` field; dashboard's `get_in_scan_for_system`
  reads it.
