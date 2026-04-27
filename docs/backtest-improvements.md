# Backtest Improvements

Suggestions and known issues that are not blocking current operation but should
be addressed when next we do a coordinated backtest + live regeneration. Leave
each item in this file until it ships, then remove or move to a changelog.

## 1. SB and W (sugar) `last_day` exits ~1 month before First Notice Day

### Status

Open. **Both backtest and live system are wrong, in the same direction, by the
same amount — so they are still aligned with each other.** Do not fix in
isolation: fixing only one side would break parity. Plan a single coordinated
change that flips both CSVs, regenerates the live JSON, and regenerates the
SB/W backtest pickles together.

### Symptom

For ICE Sugar No. 11 (`SB`) and ICE White Sugar (`W`), the system's `last_day`
falls roughly a month earlier than each contract actually stops trading on the
exchange. End-of-month pickles confirm CSI keeps quoting bars right up to the
real LTD, but `Active_Days == -1` is set far earlier, so the trailing weeks of
the contract carry `NaN` in `Active_Days` and never enter the scan window.

Concrete examples (current state, both backtest and live):

| Contract | Exchange last trade | Exchange first notice day | System `last_day` | Days early |
|---|---|---|---|---|
| SB K5 (May 2025) | 2025-04-30 | 2025-05-01 | 2025-03-28 | ~22 trading days |
| SB N6 (Jul 2026) | 2026-06-30 | 2026-07-01 | 2026-05-28 | ~23 trading days |
| W  K5 (May 2025) | 2025-04-15 | 2025-04-16 | 2025-03-28 | ~13 trading days |
| W  Q6 (Aug 2026) | 2026-07-16 | 2026-07-17 | 2026-06-29 | ~12 trading days |

ICE specs:
- Sugar No. 11: <https://www.ice.com/products/23/Sugar-No-11-Futures/specs>
  ("Last business day of the month preceding the delivery month"; FND = next
  business day)
- White Sugar: <https://www.ice.com/products/37089080/White-Sugar-Futures/specs>
  ("Sixteen calendar days preceding the first day of the delivery month";
  FND = 15 calendar days before delivery month)

### Root cause

Both systems compute `last_day` from `(last_month, last_day)` columns in their
product master CSV via the same intent: an offset into a reference month around
the contract's expiry. Sugar futures are unusual — their `lastTradeDate` falls
in the *month before* the contract month, not in the contract month itself.
That edge case interacts badly with the historical month-offset formula.

Two fixes to that interaction were attempted, on three days in February 2026,
in two different repos. Only the live one ever produced correct dates, and
that one was later reverted.

### Timeline (Feb–Apr 2026)

1. **Feb 16, 2026 — `quartet_system` `b2a9fef "update tau backfill"`**
   Edits `src/quartet/data/reference/ibkr_product_master.csv`:
   - `SB`: `last_month -1 → 0`
   - `W`:  `last_month -1 → 0`
   `last_day` left at `-2`. Combined with the existing
   `compute_last_day_standard` lm-zero branch in
   `src/quartet/contract_handler/contract_generator.py:386`, this routes SB/W
   through "count back N business days from CSI/IBKR `lastTradeDate`",
   producing `last_day = LTD - 1 bday` (April 29 for SB K5, April 14 for W K5).
   This is the correct fix.

2. **Feb 19, 2026 — `data_pipeline` `ecc3be0 "fix active timing"`**
   Edits `data_pipeline_package/scripts/transform/breakeven_labels.py` and
   `data_pipeline_package/data/reference/product_master.csv`. Two algorithm
   changes ship together:

   a. New reference-month rule for the existing month-offset branch:
      `ref_month = min(contract_month, lastTradeDate.month)` instead of just
      `contract_month`. The new code comment explicitly names SB and W as the
      motivating cases ("for products where lastTrade falls before the contract
      month (SB, W, etc.)").

   b. New `elif months_before_expiration == 0 and last_trade_date is not None`
      branch that counts back N business days from `lastTradeDate` — exactly
      the same semantics as quartet's `lm == 0` branch.

   The CSV change in this commit was unrelated to sugar (it flipped `LE`
   "Live Cattle" from `first_monday` to `first_friday`). **The `SB2` and `LSU`
   rows kept `Last Long Month = -1` and `Last Short Month = -1`.**

   Effect on SB K5:
   - Pre-`ecc3be0`: `first_of_last_day_month = May 1`,
     `idx[-2]` of dates `< May 1` = **2025-04-29**. Correct, by coincidence —
     CSI's last bar for K5 is April 30, so the upper bound was right.
   - Post-`ecc3be0`: `ref_month = min(May, April) = April`,
     `first_of_last_day_month = April 1`, `idx[-2]` of dates `< April 1` =
     **2025-03-28**. A full month too early.

   So the commit fixed a different family of products (those whose LTD is
   inside the contract month, e.g. CL/GC) and broke SB/W in the same edit.
   The new lm-zero branch (b) would have given the right answer for SB/W,
   but only fires when `last_long_month == 0`, and the CSV stayed at `-1`.

   The data_pipeline backtest pickles were last regenerated **2026-03-11**
   (~3 weeks after `ecc3be0`), so every backtest run from those pickles uses
   the wrong dates. Files affected:
   - `data_pipeline_package/data/processed/agriculture/long/sugar_11.pkl`
   - `data_pipeline_package/data/processed/agriculture/long/white_sugar.pkl`
   - their `short/` counterparts

3. **Apr 25, 2026 — `quintet_system` `e55b009 "fix data master and json"`**
   Bulk-imports `ibkr_product_master.csv` and a regenerated
   `futures_contracts_2021_2027.json` into the new quintet repo. The imported
   CSV has `SB` and `W` at `last_month = -1`. The Feb 16 quartet fix did not
   carry over. The JSON was regenerated from the regressed CSV, so live SB/W
   contracts in `src/quintet/data/reference/futures_contracts_2021_2027.json`
   carry the early `last_day` / `end_scan` / `start_scan` values.

### Why the backtest was correct before Feb 19, 2026

The pre-`ecc3be0` formula was

```
first_of_last_day_month = contract_month + (lm + 1) months   # = contract_month for lm=-1
idx = df.index < first_of_last_day_month
last_trade_day = idx[-2]
```

For SB/W this happened to work *because* lastTradeDate is in the month before
delivery: CSI's data extends through the real LTD (in the prior month), so
`idx < contract_month_start` correctly bounded the search at LTD, and `idx[-2]`
landed one bday before LTD.

It was not robust — it gave wrong answers for SB/W contracts where CSI
recorded `lastTradeDate` inside the contract month itself (anomalies seen in
e.g. `SB 1985-10`, `SB 1993-03`, `SB 2001-10`, `SB 2005-07`) — but for the
overwhelming majority of contracts it produced the right number.

So the answer to "when was the backtest correct?" is:

- **Initial commit through 2026-02-18:** correct for typical SB/W contracts
  (last_day = LTD − 1 bday), wrong for a handful of historical anomalies.
- **2026-02-19 (`ecc3be0`) onward:** uniformly wrong for SB/W (last_day ≈ a
  month before LTD) until the planned fix below ships.

Live system was always built off the same kind of `lm=-1` formula via quartet's
generator, with one correct interval:

- **Initial through 2026-02-15:** wrong (same coincidental shape as backtest
  pre-`ecc3be0`, but driven through quartet's own algorithm).
- **2026-02-16 to 2026-04-24:** correct in quartet (`lm=0` for SB/W).
- **2026-04-25 onward (quintet):** wrong again after the master copy.

### Planned fix

The algorithm branch needed (`lm == 0` → count back N bdays from
`lastTradeDate`) is **already implemented in both repos** —
`quartet_system/src/quartet/contract_handler/contract_generator.py:386` and
`data_pipeline/data_pipeline_package/scripts/transform/breakeven_labels.py`
(the `elif months_before_expiration == 0 and last_trade_date is not None`
branch). No code changes are required. Only the CSV inputs need to flip.

Two CSV edits, then regenerate derived artifacts:

1. **`data_pipeline_package/data/reference/product_master.csv`**
   - `SB2` row: `Last Long Month: -1 → 0`, `Last Short Month: -1 → 0`
   - `LSU` row: `Last Long Month: -1 → 0`, `Last Short Month: -1 → 0`
   - `Last Long Day` and `Last Short Day` stay `-2` on both rows.

2. **`src/quintet/data/reference/ibkr_product_master.csv`**
   - `SB` row: `last_month: -1 → 0`
   - `W`  row: `last_month: -1 → 0`
   - `last_day` stays `-2` on both rows.

3. Regenerate live JSON: rerun the contract generator
   (`quartet_system/src/quartet/contract_handler/contract_generator.py`)
   for SB and W and write back to
   `src/quintet/data/reference/futures_contracts_2021_2027.json`.

4. Regenerate backtest pickles: rerun the data_pipeline transforms for the
   sugar products to produce updated:
   - `data_pipeline_package/data/processed/agriculture/long/sugar_11.pkl`
   - `data_pipeline_package/data/processed/agriculture/long/white_sugar.pkl`
   - `data_pipeline_package/data/processed/agriculture/short/sugar_11.pkl`
   - `data_pipeline_package/data/processed/agriculture/short/white_sugar.pkl`

5. Re-run any downstream notebooks that consume the sugar pickles
   (`final_commodities_4.ipynb`, `final_commodities_short_4.ipynb`, and the
   combined backtest in `combined_systems_plus_short.ipynb`) so model
   artifacts and the combined-systems backtest are both rebuilt against the
   corrected SB/W timing.

### Verification

After the fix, expected `last_day` values for the next few SB/W contracts:

| Contract | Expected `last_day` | Expected `last_day` source |
|---|---|---|
| SB N6 | 2026-06-29 | LTD 2026-06-30 − 1 bday |
| SB V6 | 2026-09-29 | LTD 2026-09-30 − 1 bday |
| SB H7 | 2027-02-25 | LTD 2027-02-26 − 1 bday |
| W  Q6 | 2026-07-15 | LTD 2026-07-16 − 1 bday |
| W  V6 | 2026-09-14 | LTD 2026-09-15 − 1 bday |
| W  Z6 | 2026-11-12 | LTD 2026-11-13 − 1 bday |

Cross-check against ICE specs and the CSI `last_trade_dates` map already
embedded in `sugar_11.pkl` / `white_sugar.pkl`.

### Why this is left alone for now (2026-04-27)

Backtest and live system both encode the same wrong dates, so paper P&L and
the live signals remain mutually consistent. Fixing only one side breaks
parity (memory: `feedback_backtest_parity.md`) and would invalidate
walk-forward statistics. Schedule (1)–(5) as a single coordinated change.
