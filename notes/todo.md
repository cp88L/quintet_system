# Quintet — open work as of 2026-04-28

## Done this session

- **SR3 scan windows**: master CSV (`last_month=-3, last_day=-3, buffer=60`) and JSON registry regenerated for SR3 only. Backtest sync logged in `docs/backtest-improvements.md` §2.
- **`--trim-today` flag**: drops today's still-open partial bar before Steps 1–3. Wired in `run/__main__.py`, applied in `process_contracts/processor.py`.
- **Tau (Wilson lower-bound walkdown)** end-to-end:
  - `tau/threshold.py` — `wilson_lower_bound`, `calculate_threshold`, `compute_system_tau`. Pools all products per system, no `MAX_CONTRACTS`, no `DEFAULT_TAU` fallback.
  - `tau/lookback_builder.py` — refresh + persist per-product 60-bar parquets at `data/processed/{system}/_lookback/{product}.parquet`. Incremental: rebuild only when newest expired contract changes.
  - `tau/__init__.py` re-exports both.
  - `run/__main__.py:step_taus` — Step 4 runs across all 5 systems, prints summary, writes `data/processed/{system}/_tau.json`.
- **Label formula aligned to data_pipeline**:
  - `tau/label_calculator.py` — `_entry_levels_long` and `_entry_levels_short` switched to `risk_pts = prev_close − sup` / `res − prev_close`; shift-compute-unshift logic in `add_labels` unchanged (decision-row convention preserved).
  - `config.py` — `TARGET_MARGIN: 0.10 → 0.02`.
  - Verified byte-for-byte across 240 contracts × 3 windows × 383k rows (long + short universes) — labels and entry levels match `data_pipeline.BreakevenLabelCalculator` exactly after one-row alignment shift.
- **Helper script & memory**:
  - `quintet_storage/tools/regen_product_scan_windows.py` — surgical per-product registry rewrite mirroring `02_scan_contracts.ipynb`.
  - Memory: `scan_window_regen.md` indexed in `MEMORY.md`.

## Bugs identified, not fixed

1. **data_pipeline `TARGET_MARGIN = 0.02` is a regression.** Commit `e3085a8` "add short side" (2026-03-14) flipped it from 0.10 → 0.02 inside a giant unrelated commit. The optimized backtest run on `c654249` → `ecc3be0` (2025-12-27 → 2026-02-19) used 0.10. Quintet currently matches the regressed 0.02 for parity. To restore the optimized regime: revert `data_pipeline_package/config.py:23` to 0.10, regenerate every entries parquet + processed pickle, retrain XGBoost models, re-derive `PRECISION` per system, then mirror the same in quintet's `config.py`.
2. **Stale `_clusters.parquet` files were deleted earlier in the session.** `make_predictions/clusters.py` does not write them; today's run produces only in-memory cluster output. If a downstream consumer ever expected the file, that's a gap.

## Next steps (priority order)

1. **Wire the tau + cluster gate.** Step 4 today computes `tau` per system and the cluster step computes per-product cluster ids per system, but neither is *applied*. Need a "Step 5: Signals" that:
   - For each system, finds today's in-scope contract per product (the one with `start_scan ≤ today ≤ end_scan`).
   - Reads its today-row `prob`.
   - Marks `gate_pass = (prob ≥ tau) AND (cluster_id ∈ INCLUDE_CLUSTERS[system])`.
   - Returns / persists the actionable per-product list per system.
2. **Compute stop-entry prices and unit counts.** For each gate-passing product:
   - Long: stop-buy at `Res_N + LIMIT_OFFSET`.
   - Short: stop-sell at `Sup_N − LIMIT_OFFSET`.
   - Unit count: `floor(equity * HEAT[system] / ((Res_N − Sup_N) * point_value))`.
3. **IBKR order placement.** Subclass `EClient`/`EWrapper` per the no-`ib_async` rule, submit stop orders for tomorrow's session. Reuse the existing `historical_bars.py` connection plumbing.
4. **Tau-history append log.** Today `_tau.json` is overwritten each run. To chart tau-over-time, add a `_taus_history.parquet` per system that appends a row each run.

## Decisions pending

- **Coordinate-revert TARGET_MARGIN to 0.10?** Big change (every backtest pickle, every model, all `PRECISION` values). Worth it if 0.10 was the optimized regime.
- **Recalibrate `PRECISION` targets?** Today only C4 passes the gate (tau=0.2088, target=0.3202). CS4/E4/E7/E13 all NaN because pool base rate is below target. Either accept "no signal those systems today" or retrain/recalibrate.
- **`LIMIT_OFFSET = 0.000` (config.py:56)** — currently no buffer above resistance / below support for stop entries. Confirm intentional before going live.

## Where to look on resume

- `docs/backtest-improvements.md` — running log of live↔backtest divergences (SB/W §1, SR3 §2).
- `notes/cluster_missing_data.md` — known cluster-pool behavior on missing days.
- `quintet_storage/tools/regen_product_scan_windows.py` — surgical scan-window regen helper.
- `data/processed/{system}/_lookback/*.parquet` — 60-bar tau pools for charting.
- `data/processed/{system}/_tau.json` — latest tau snapshots.
