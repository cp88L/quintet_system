# Trade Flow Architecture Spec

## Purpose

Quintet already has a working signal pipeline. The next layer should add
trade management without turning the scanner into an order-management layer
and without spreading IBKR objects through the business logic.

The design goal is one staged daily run:

```text
1. Compute signals      (existing pipeline stages)
2. Collect broker state (IBKR — single source of truth)
3. Reconcile broker state into per-(con_id, system) state
4. Plan maintenance     (signal-independent intents)
5. Build trade plan     (signal-dependent intents)
6. Execute and record   (dry-run or live)
```

This is an end-of-day process. It runs during the market break, and
development can use `--trim-today` so yesterday's complete bar is the active
decision row. Because of that, the architecture does not need an overbuilt
live-intraday market-state snapshot. Broker state is collected from IBKR each
run, kept broker-neutral, and used to produce the latest plan/report.

The signal stages and trade stages run in **one process**. Signal results are
handed to trade stages in memory, not via files. `_funnel.json` is still
written as a side-effect for dashboard/forensics, but nothing reads it back.

## Terms

- **Flow**: the ordered orchestration for a run.
- **Module**: reusable code called by a flow.
- **Daily Flow**: the one orchestrator for a daily run — signal stages, then
  trade stages, in memory.
- **Broker adapter**: the only layer allowed to import IBKR SDK objects.
- **Business logic**: broker-neutral decision code.
- **Local operational files**: small latest-run outputs. IBKR remains the
  source of truth for positions and open orders.

## Non-Goals

- Do not rewrite the existing signal pipeline first.
- Do not put IBKR `Contract`, `Order`, `EClient`, or callback objects in
  trading modules.
- Do not build a single `OrderManager` class that syncs, sizes, cancels,
  modifies, places, exits, reports, and records outputs.
- Do not collect live price data for the full tradable universe.
- Do not make the scanner responsible for broker state.
- Do not maintain locally-cached broker state across runs. IBKR is the
  source; rebuild from `reqAllOpenOrders` / `reqPositions` each run.
- Do not block on per-order acknowledgment. `placeOrder` is fire-and-forget;
  truth-of-state is delegated to the next run's reconcile.

## Current Quintet Boundary

The current signal pipeline lives under `src/quintet/pipeline/` and is
orchestrated by `src/quintet/run/__main__.py`.

Current stage order:

```text
Fetch
-> Indicators
-> Predictions
-> BuildFunnel
-> Tau
-> Clusters
-> Breakout
-> Snapshot
```

`PositionStage` is removed in this architecture: held-position gating moves
into the trade-flow reconciler, which is the single source of truth for what
is held vs. what is pending.

The current snapshot:

```text
src/quintet/data/processed/_funnel.json
```

is written as a write-only artifact for dashboard consumption and forensic
inspection. The trade flow does not read it; signal candidates are handed to
trade stages in memory inside the same daily run.

## High-Level Layout

Add trade-related modules without moving the existing signal pipeline first:

```text
src/quintet/
  flows/
    daily.py           single daily orchestrator (signal + trade)

  trading/
    models.py          broker-neutral domain models (incl. RiskState)
    reconcile.py       broker state classification (no safety supercategory)
    maintain.py        signal-independent intents (last_day exit + roll, orphans, alerts)
    planner.py         signal-dependent intents (trail, modify, cancel-stale, place)
    risk.py            sizing and pooled-equity / pooled-risk budget

  broker/
    gateway.py         broker-neutral interface/protocol
    models.py          BrokerState, BrokerPosition, BrokerOrder, BrokerFill, AccountState
    ibkr/
      client.py        raw IBKR connection and callbacks
      mapper.py        IBKR objects <-> broker-neutral models
      orders.py        order intents -> IBKR Contract/Order objects
      errors.py        IBKR error classification

  execution/
    models.py          order/cancel/modify/exit intents
    dry_run.py         no broker side effects
    ibkr.py            executes approved intents via BrokerGateway

tests/
  trading/             pure-function tests for sizing, classification, planning
  broker/              broker adapter tests against fakes
  execution/           dry-run / live executor parity tests
```

The exact package names can change, but the dependency direction should not.

The flow stays thin. It chooses the order of operations, passes data
between modules, and records run outputs. Modules do not call flows, and
business-rule modules do not perform broker side effects.

Allowed dependency direction:

```text
flows -> trading modules -> broker-neutral models
flows -> broker gateway interface
flows -> executor
executor -> broker gateway interface
broker.ibkr -> ibapi
```

Forbidden dependency direction:

```text
trading -> broker.ibkr
trading -> ibapi
pipeline -> broker.ibkr
pipeline -> execution
```

## OOP Rules

Use classes for lifecycle, stateful IO, and orchestration. Use functions for
decision rules.

Good class boundaries:

```text
DailyFlow
BrokerGateway
IBKRClient
ReportStore
OrderExecutor
DryRunExecutor
```

Good function boundaries:

```text
reconcile_state(...)
plan_maintenance(...)
plan_trade(...)
calculate_position_size(...)
calculate_risk_budget(...)
classify_order(...)
build_order_intents(...)
```

Good data boundaries:

```text
BrokerState
ReconciledTradeState
RiskState               # account_equity, portfolio_risk
SignalCandidate
TradePlan
ExecutionReport
```

Avoid broad manager classes. If a class owns broker sync, risk sizing, stale
order detection, stop updates, new orders, exits, reports, and output writing,
it is too large.

## Daily Flow

### 1. Compute Signals

Run the existing pipeline stages (Fetch → Indicators → Predictions →
BuildFunnel → Tau → Clusters → Breakout → Snapshot). Snapshot writes
`_funnel.json` as a side-effect. The in-memory funnel is forwarded to the
trade stages directly; the file is never read back.

The output handed forward is a set of per-system actionable
`SignalCandidate` objects.

### 2. Collect Broker State

Inputs:

```text
BrokerGateway
TradeConfig
```

Broker calls needed:

```text
reqPositions
reqAllOpenOrders
reqAccountSummary
reqContractDetails only for held/pending contracts that need metadata
```

`reqExecutions` is not used in v1: with `orderRef`-based attribution from
current open orders, executions are not needed for system attribution. Add
later only if a feature requires it.

Output:

```text
BrokerState
  collected_at
  account: AccountState
  positions: list[BrokerPosition]
  open_orders: list[BrokerOrder]
  recent_errors: list[BrokerError]
  contract_meta: dict[int, ContractMeta]
```

`BrokerState` is broker-neutral; raw IBKR objects do not leave
`broker/ibkr/`.

### 3. Reconcile Broker State

Inputs:

```text
BrokerState
```

Output:

```text
ReconciledTradeState
```

Primary key:

```text
(con_id, system)
```

Use the system alias, not the numeric label. Quintet has `C4`, `CS4`, and
`E4` sharing label `4`, so `(con_id, label)` is not enough.

System attribution comes from `orderRef = VOICE_MAP[system]` on the open
order (entry or protective stop). On read-back, `VOICE_TO_SYSTEM[orderRef]`
recovers the system alias.

Order classification is side-aware. Do not classify purpose from action
alone:

```text
long system  (C4, E4, E7, E13):  entry = BUY,  protective stop = SELL
short system (CS4):              entry = SELL, protective stop = BUY
```

Reconciliation produces the following buckets:

```text
positions_by_key
entry_orders_by_key
protective_stops_by_key
orphaned_orders
unknown_system_positions       # report-only; do not gate planning
external_or_unclassified_orders # report-only; do not gate planning
```

Held positions whose system attribution cannot be recovered from any current
order are reported as `unknown_system_positions`. They do **not** participate
in planner gating: each system's `(con_id, system)` gate is independent.

### 4. Plan Maintenance (Signal-Independent)

Inputs:

```text
ReconciledTradeState
TradeConfig
contract calendar / expiry metadata as needed
```

Output:

```text
MaintenancePlan
```

Intents produced here do not depend on today's signals:

```text
LastDayCloseoutIntent        # last_day exit + (conditional) roll-entry bundle
CancelOrphanedStopIntent     # stops with no parent and no held position
AlertMissingStopIntent       # report-only; never autocreates a stop in v1
NoopIntent
```

Required checks:

```text
Is any held contract's next RTH trading day at or beyond its final allowed trading day?
Are there orphaned protective stops?
Does every open position have a protective stop? (alert only)
```

#### Last-day exit + conditional roll

The IBKR adapter reads each held contract's `liquidHours`, parses the next
regular trading session date, and stores only that broker-neutral
`next_rth_day` in `BrokerState`. When `next_rth_day >= last_day`, the
maintenance planner produces a single `LastDayCloseoutIntent` describing the
close-and-roll bundle. This matches Quartet's day-before placement behavior:
an EOD/break run before `last_day` can stage the RTH open closeout while the
replacement stop remains live in extended hours.

```text
LastDayCloseoutIntent
  key: (con_id, system)
  side
  symbol
  old_local_symbol
  old_protective_stop_cancel:
    stop_order_id            # existing live stop
  replacement_protective_stop:
    order_type = existing stop type
    outsideRth = True
    tif        = "GTC"
    transmit   = False
    action     = SELL (long) | BUY (short)
    aux_price  = existing stop aux_price
    lmt_price  = existing stop lmt_price, if applicable
    oca_group  = "ROLL_<con_id>_<system>_<date>"
    oca_type   = 1              # cancel-others-on-fill
  old_market_exit:
    order_type = "MKT"
    outsideRth = False
    tif        = "GTC"
    action     = SELL (long) | BUY (short)
    transmit   = True
    oca_group  = same as replacement stop
  roll_entry:                # populated only if ROLL_ENABLED[s] AND
                             # new_contract.RSpos_N >= ROLL_RSPOS_MIN[s]
    new_local_symbol
    new_con_id
    parent:
      order_type = "MKT"
      outsideRth = False
      tif        = "GTC"
      transmit   = False
      action     = BUY (long) | SELL (short)
    child_stop:
      order_type = "STP"
      outsideRth = True
      tif        = "GTC"
      transmit   = True
      parentId   = parent.order_id
      aux_price  = new_contract.Sup_N (long) | new_contract.Res_N (short)
```

Mechanics:

- The close side uses Quartet's replace-stop pattern: cancel the existing
  protective stop, place a replacement protective stop with the OCA group and
  `transmit=False`, then place the market exit with the same OCA group and
  `transmit=True`.
- Whichever fills first (the replacement stop during ETH, or the market exit
  at RTH open) cancels the other.
- The roll entry, when present, is a parent/child bracket with a `MKT
  outsideRth=False` parent — IBKR holds the bundle until RTH opens and the
  parent fills, at which point the child stop activates.
- Commodities (`C4`, `CS4`) have `ROLL_ENABLED = False` and never produce a
  `roll_entry`.

### 5. Build Trade Plan (Signal-Dependent)

Inputs:

```text
SignalCandidates (in-memory, from step 1)
ReconciledTradeState
RiskState
TradeConfig
```

Output:

```text
TradePlan
```

Intents produced here depend on today's signals and current broker state:

```text
ModifyPositionStopIntent     # trail held position's stop to current Sup_N/Res_N
CancelStaleEntryIntent       # signal disappeared
ModifyEntryIntent            # entry level moved (tick-rounded)
ModifyPendingStopIntent      # pending bracket's child stop level moved
PlaceBracketIntent           # new entry on actionable signal
```

#### Per-`(con_id, system)` decision table

```text
held position + signal exists       -> modify position stop if Sup_N/Res_N tick-changed
held position + no signal           -> modify position stop if Sup_N/Res_N tick-changed
pending entry + signal exists       -> modify entry/stop if either tick-changed
pending entry + no signal           -> cancel entry (auto-cancels child stop)
no position, no entry + signal      -> place new bracket
no position, no entry + no signal   -> noop
```

A new bracket intent is generated for `(con_id, system)` only when no held
position and no pending entry exist for that key. Missing stops, orphaned
stops, and unknown attribution do not gate this decision; they are alerts.

#### Trail-stop policy

Stops on held positions are always re-aligned to the system's current
structural level — both directions, not trail-only-favorable. The model's
`Sup_N` (long) / `Res_N` (short) is the canonical "structure" view for that
system; if it falls, the stop falls with it.

Modify trigger: only when `round_to_tick(new_level, min_tick) !=
current_stop.aux_price`. This prevents order flapping when the level wiggles
within a tick.

#### For long systems (C4, E4, E7, E13)

```text
entry_price       = Res_N
protective_stop   = Sup_N
entry action      = BUY
protective action = SELL
```

#### For short systems (CS4)

```text
entry_price       = Sup_N
protective_stop   = Res_N
entry action      = SELL
protective action = BUY
```

#### Risk sizing (pooled equity, pooled risk)

```text
portfolio_risk = sum over ALL open positions across ALL systems of
                 (current_price - stop_price) / price_magnifier * multiplier * |qty|
                 (sign-adjusted for short positions)

free_equity = net_liquidation - portfolio_risk

budget[s]   = max(0, free_equity * HEAT[s])

risk_per_contract = abs(entry_price - stop_price) / price_magnifier * multiplier

quantity    = floor(budget[s] / risk_per_contract)
```

There is one pooled equity account and one pooled risk number. `HEAT[s]`
is the per-system fraction applied to the *same* free-equity pool — weights
on a common pool, not separate buckets. Existing positions in any system
shrink the pool for every system that fires today.

#### Skip reasons

The canonical list when a `PlaceBracketIntent` cannot be produced for an
actionable signal:

```text
already_has_position         # (con_id, system) is held
already_has_entry_order      # (con_id, system) has a pending bracket
insufficient_risk_budget     # floor(budget / risk_per_contract) == 0
```

`negative_free_equity` collapses into `insufficient_risk_budget` via
`max(0, ...)`. `degenerate_risk` and `missing_price_levels` cannot occur —
the former requires zero range over the structure window, the latter is
filtered upstream by `BuildFunnelStage`.

### 6. Execute And Record Results

Inputs:

```text
TradePlan
Executor
ReportStore
```

Executors:

```text
DryRunExecutor
IBKRExecutor
```

Output:

```text
ExecutionReport
```

#### Fire-and-forget execution

The executor does not block on order acknowledgment. Each `placeOrder` is
recorded as submitted on synchronous return (or as `place_threw` on
exception). Asynchronous `error` and `orderStatus` callbacks tied to this
run's order ids are buffered as they arrive. At session end, the executor
drains the buffer and merges it into the report.

```text
1. Connect, request nextValidId, reserve N order ids upfront.
2. For each intent:
     try placeOrder(...) -> record (order_id, "submitted")
     except -> record (order_id, "place_threw", exc)
3. Brief drain window (~1s) for late callbacks tied to this run's order ids.
4. Run one same-session `reqAllOpenOrders` refresh and include the broker's
   immediate open-order view in the report.
5. Disconnect.
6. ExecutionReport = submitted-set u session callback buffer (errors, fills)
   + immediate open-order view.
```

Truth-of-state is delegated to the next run's `reqAllOpenOrders`. The
planner's `(con_id, system)` gate makes repeated runs safe: if a placement
silently failed at the broker but never raised, the next run will see no
order on that key and re-evaluate.

The same-session open-order refresh is report-only. It is not durable state
and is not used by the next run.

Record:

```text
latest_trade_plan.json
latest_execution_report.json
```

The dry-run executor uses the same `TradePlan` as live execution and
produces the same report shape without broker side effects.

## Broker Adapter API

Keep the broker adapter small. It exposes operations the flow needs, not
every IBKR capability.

```python
class BrokerGateway:
    def collect_broker_state(self) -> BrokerState:
        ...

    def get_next_order_ids(self, count: int) -> list[int]:
        ...

    def submit_orders(self, batch: OrderBatch) -> ExecutionResult:
        ...

    def cancel_orders(self, order_ids: list[int]) -> ExecutionResult:
        ...

    def modify_orders(self, intents: list[ModifyOrderIntent]) -> ExecutionResult:
        ...
```

`submit_orders` / `cancel_orders` / `modify_orders` are fire-and-forget; the
returned `ExecutionResult` reports synchronous outcomes only (submitted,
threw, or cancel/modify acknowledged at the API level). Asynchronous
callbacks land in a session-scoped buffer accessible via the gateway.

IBKR implementation details stay inside `broker/ibkr/`.

Required IBKR calls:

```text
connect / disconnect / run loop
nextValidId
reqAutoOpenOrders
reqPositions
reqAllOpenOrders
reqAccountSummary
reqContractDetails
placeOrder
cancelOrder
orderStatus
error
```

The daily broker-state session must use configured `CLIENT_ID = 0`. IBKR
client 0 can see and bind manual TWS/Gateway orders, which is required because
the flow treats current broker state, including trades entered outside
Quintet, as the source of truth.

Defer these unless needed by a specific feature:

```text
reqExecutions
reqMktData
gap handling near close
intraday order-status scheduler
```

At EOD, current prices for risk can come from the latest processed close,
matching the stable-bar assumption. Live market data can be added later for
a specific operational check rather than becoming a planner dependency.

## State Files

Do not maintain durable state across runs. IBKR is the source for positions,
open orders, executions, and account values. The trade flow rebuilds these
each run.

The only files written are the two latest-run reports:

```text
latest_trade_plan.json
latest_execution_report.json
```

Both are overwrite-each-run. There is no append-only rejection log in v1;
rejections live in the run's `latest_execution_report.json`. If forensic
"what rejected last week" becomes a real question later, add a separate
append log then.

`DataPaths` exposes:

```text
positions_json
orders_json
rejections_json
funnel_json
```

`positions_json` and `orders_json` may be used as temporary inspection files
during development, but the design does not depend on them as durable state.
If historical audit or replay becomes important later, add
`data/runs/{run_id}/` then.

## Configuration

Existing config values that should be reused:

```text
SYSTEMS
SYSTEM_LABEL
SYSTEM_SIDE
VOICE_MAP
VOICE_TO_SYSTEM
HEAT
LIMIT_OFFSET
ROLL_ENABLED
ROLL_RSPOS_MIN
```

Add only when needed:

```text
CONTRACT_DETAILS_TIMEOUT_SECONDS
ALLOW_LIVE_EXECUTION
DRY_RUN_DEFAULT
```

Broker error classification stays inside `broker/ibkr/errors.py` rather than
global config.

## Implementation Phases

### Phase 1: Spec Models And Dry-Run Plan

Deliver:

```text
broker-neutral trade/execution dataclasses
RiskState dataclass
latest trade-plan/report writer
DailyFlow dry-run mode (signal stages run, trade stages run with fake/in-memory broker state)
```

No IBKR writes.

Acceptance:

```text
python -m quintet.run --dry-run
```

runs the daily flow end-to-end against a fabricated `BrokerState`, builds a
broker-neutral `TradePlan` with skip reasons, and writes
`latest_trade_plan.json`.

### Phase 2: Broker State And Reconciliation

Deliver:

```text
IBKR collect_broker_state()
BrokerState mapping
reconcile_state()
```

Acceptance:

```text
open positions are keyed by (con_id, system)
open orders are classified as entry / protective / orphaned / external
unknown attribution is reported but does not gate planning
```

### Phase 3: Maintenance Planning

Deliver:

```text
last-day exit + conditional roll bundle (Quartet replace-stop OCA pattern,
  next_rth_day >= last_day trigger, MKT outsideRth=False exit,
  parent/child new-entry)
orphaned-stop cancellation intents
missing-stop alerts
unclassified-order alerts
```

Acceptance:

```text
existing exposure is handled before new-entry planning
dry-run output makes every signal-independent action auditable
ROLL_ENABLED gating works (commodities never produce a roll_entry)
```

### Phase 4: Trade Plan Planning

Deliver:

```text
side-aware bracket intents
pooled-equity / pooled-risk sizing using HEAT[s]
tick-rounded modify trigger for trail and pending-entry mods
duplicate position/order gates ((con_id, system))
position stop-update intents
pending-entry cancel/modify intents
explicit skip reasons (3-item canonical list)
```

Acceptance:

```text
C4/E4/E7/E13 generate long-side intents
CS4 generates short-side intents
no new bracket intent is created for an existing (con_id, system) position/order
trail-stop modify fires only when tick-rounded value changed
```

### Phase 5: Live Execution

Deliver:

```text
IBKRExecutor (fire-and-forget)
order id allocation from nextValidId
submit bracket orders
cancel orders
modify orders
roll-exit replace-stop OCA sequence
async callback drain into ExecutionReport
same-session open-order refresh into ExecutionReport
execution rejection reporting
```

Acceptance:

```text
dry-run and live execution consume the same TradePlan shape
live execution records broker order ids and errors
re-running uses broker state and does not duplicate orders
```

### Phase 6: Optional Operational Features Later

Only after the EOD order path is stable:

```text
gap handling
near-close scheduler
live reqMktData checks
per-run artifact directories
missing-stop auto-create intent
append-only rejection log
```

These are intentionally outside the first version.

## Quartet Lessons To Keep

Useful patterns from quartet:

```text
single connection for related broker operations
sync open orders from IBKR as source of truth
classify open orders by purpose
record execution rejections in the run report
use orderRef for system attribution
use dry-run before live placement
```

Patterns to avoid copying directly:

```text
multiple overlapping IBKR clients
business logic inside IBKR client classes
large order manager class
long-only assumptions
printing as the primary report mechanism
mixing signal collection and order execution
durable cross-run rejection log (deferred to a later phase)
manual-label / cached attribution fallback
per-order ack waiting
```

## Quartet Reuse Plan

Use quartet as a reference implementation, not as a package to copy
wholesale. Copy small proven mechanics. Rewrite anything that mixes
orchestration, business rules, broker calls, persistence, or old
system-label assumptions.

### Copy Mostly As-Is

These are small enough to port directly with light renaming:

```text
round_to_tick(price, min_tick)
calculate_position_size(...)   # adjust to pooled-equity / pooled-risk shape
IBKR connection thread / callback event pattern
```

Source references:

```text
quartet/place_orders/orders.py
quartet/risk_budget/position_sizer.py
quartet/risk_budget/calculator.py
quartet/contract_handler/unified_client.py
```

### Copy The Idea, Rewrite For Quintet

These are useful concepts, but the quartet code has the wrong shape for
quintet:

```text
Order construction
  Keep: parent/child bracket mechanics, transmit=False/True.
  Rewrite: side-aware actions for long and short systems.
  Add:    MKT outsideRth=False parent for roll entries; Quartet replace-stop
          OCA pattern for the roll exit.

Order classification
  Keep: classify entry, pending protective stop, position protective stop,
        orphaned stop, exit, unknown.
  Rewrite: use (con_id, system), not (con_id, label), and classify with
           side awareness.

Set-diff order planning
  Keep: compare current pending entries to current signals.
  Rewrite: put it in trading/planner.py as pure functions.

Execution attribution
  Keep: orderRef -> system attribution via VOICE_MAP[system].
  Rewrite: no manual-label or cache fallback in v1; missing attribution is
           a report-level alert, not a planning gate.

Rejection tracking
  Keep: record order id, con_id, system, action, error code/message.
  Rewrite: emit into latest_execution_report.json, not a separate tracker.

Risk budget arithmetic
  Keep: portfolio risk and available risk concepts.
  Rewrite: pooled equity and pooled risk; HEAT[s] is the per-system fraction
           applied to the shared free-equity pool.
```

### Write Fresh

These should be quintet-native:

```text
DailyFlow orchestration (signal + trade in one process, in-memory handoff)
BrokerState dataclasses
ReconciledTradeState dataclasses
RiskState dataclass
TradePlan dataclasses
ExecutionReport dataclasses
reconcile_state(...)
plan_maintenance(...)
plan_trade(...)
DryRunExecutor
side-aware bracket intent builder
roll-bundle intent builder (OCA exit + parent/child new-entry)
fire-and-forget IBKRExecutor with async callback drain
```

### Do Not Copy

Avoid these quartet shapes in the first version:

```text
order_manager.py
full OrderTracker class
manual label / cached attribution fallback
gap handling and near-close scheduler
multiple overlapping IBKR clients
long-only order classification
JSON persistence as source of truth
per-order ack timeouts
durable append-only rejection log
```

The target is one small quintet broker adapter, not `OrderClient`,
`IBClient`, and `UnifiedIBClient` all over again.

## Step-By-Step Build Plan

### Step 1: Port Pure Utilities

Create small modules first:

```text
trading/risk.py
trading/prices.py
```

Move/adapt:

```text
round_to_tick(price, min_tick)
calculate_position_size(...)        # pooled-equity / pooled-risk shape
calculate_risk_budget(...)          # pooled risk across all systems
```

Acceptance:

```text
unit tests cover tick rounding and sizing for long/short systems
pooled-risk math is verified against multi-position fixtures
no IBKR imports
```

### Step 2: Define Broker-Neutral Models

Create:

```text
broker/models.py
execution/models.py
trading/models.py
```

Models:

```text
BrokerState
BrokerPosition
BrokerOrder
BrokerFill
BrokerError
ContractMeta
SignalCandidate
ReconciledTradeState
RiskState
TradePlan
ExecutionReport
PlaceBracketIntent
CancelOrderIntent
ModifyOrderIntent
ExitPositionIntent           # includes roll bundle
AlertIntent
```

Acceptance:

```text
models import no IBKR SDK types
keys use (con_id, system)
side is explicit on signals, positions, and order intents
```

### Step 3: Wire SignalCandidate From The Pipeline

Create:

```text
trading/signals.py             # in-memory candidate enrichment
```

Behavior:

```text
take the in-memory funnel from the pipeline run
convert each row into a SignalCandidate
derive side from SYSTEM_SIDE
derive entry/stop prices from Res_N/Sup_N by side
enrich with multiplier, min_tick, currency, exchange from ProductMaster
```

Acceptance:

```text
C4/E4/E7/E13 candidates are long
CS4 candidates are short
ProductMaster fields are present on every candidate
```

### Step 4: Build Dry-Run Daily Flow Without IBKR

Create:

```text
trading/reconcile.py
trading/maintain.py
trading/planner.py
execution/dry_run.py
flows/daily.py
```

Use a fabricated `BrokerState` first.

Acceptance:

```text
python -m quintet.run --dry-run
runs the existing pipeline stages
hands candidates in memory to the trade stages
builds a TradePlan
prints/writes latest_trade_plan.json
does not connect to IBKR
```

### Step 5: Add Minimal IBKR Broker Adapter

Create:

```text
broker/gateway.py
broker/ibkr/client.py
broker/ibkr/mapper.py
broker/ibkr/errors.py
```

Port only the needed subset of quartet's `UnifiedIBClient`:

```text
connect / disconnect / run loop
nextValidId
reqAutoOpenOrders
reqPositions
reqAllOpenOrders
reqAccountSummary
reqContractDetails
orderStatus
error
```

Use the configured client id and require it to be `0` for the daily
broker-state flow. Do not introduce a separate account/position client id for
production state collection; that is how manual/outside-system orders get
missed.

Acceptance:

```text
collect_broker_state() returns BrokerState
raw IBKR objects do not leave broker/ibkr
no order placement yet
```

### Step 6: Reconcile Real BrokerState

Implement:

```text
reconcile_state(broker_state)
side-aware order classification
orderRef -> system mapping using VOICE_TO_SYSTEM
missing-stop alerts (report-only)
unknown-attribution alerts (report-only)
orphaned-stop alerts / cancellation intents
```

Acceptance:

```text
open positions are keyed by (con_id, system)
open orders are classified without long-only assumptions
unknown attribution does not block any system's planning
```

### Step 7: Plan Maintenance And Trade Plan

Implement pure planning:

```text
LastDayCloseoutIntent (last_day exit + conditional roll bundle)
ModifyPositionStopIntent (trail to current Sup_N/Res_N, tick-rounded)
CancelStaleEntryIntent (signal disappeared)
ModifyEntryIntent / ModifyPendingStopIntent (tick-rounded)
PlaceBracketIntent (side-aware, pooled-equity sized)
explicit skip reasons (3-item canonical list)
```

Acceptance:

```text
held positions block new brackets for the same (con_id, system)
pending entries are modified or cancelled rather than duplicated
CS4 generates SELL entry / BUY protective intents
long systems generate BUY entry / SELL protective intents
roll entries fire only when ROLL_ENABLED[s] AND RSpos meets threshold
trail-stop modify fires only on tick-rounded change
```

### Step 8: Add IBKR Execution

Create:

```text
execution/ibkr.py
broker/ibkr/orders.py
```

Port/rewrite order mechanics:

```text
build IBKR Contract from intent
build side-aware entry order
build side-aware protective stop order
build MKT outsideRth=False exit and replace-stop OCA pair
build MKT outsideRth=False parent + STP child for roll entries
allocate order ids
place parent with transmit=False, child with transmit=True
cancel order
modify existing order by placeOrder(existing_order_id, ...)
async error / orderStatus callback drain
same-session reqAllOpenOrders report refresh
```

Acceptance:

```text
DryRunExecutor and IBKRExecutor consume the same TradePlan
ExecutionReport records submitted order ids and broker errors
re-running uses broker state and does not duplicate orders
```

### Step 9: Add Optional Operational Features Later

Only after the EOD order path is stable:

```text
gap handling
near-close scheduler
live reqMktData checks
per-run artifact directories
missing-stop auto-create intent
append-only rejection log
```

These are intentionally outside the first version.

## Decisions

1. `PositionStage` is removed in this architecture. Reconcile is the single
   source of truth for position/order gating.
2. Do not maintain locally-cached broker state across runs. Rebuild
   positions and open orders from IBKR each run; write only the two latest
   reports.
3. Missing protective stops are alert-only in v1. Do not create stops
   automatically; report clearly. Do **not** block planning on missing-stop
   state.
4. Keep `LIMIT_OFFSET = 0.000` for the first live-order version. Add a
   buffer later only if operational fills show that exact stop-limit prices
   are a problem.
5. Sizing pools equity and risk across all systems. `HEAT[s]` is the
   per-system fraction applied to the shared free-equity pool, not
   per-system buckets.
6. Multi-system on the same `con_id` produces independent brackets per
   `(con_id, system)`, attributed via `orderRef = VOICE_MAP[system]`.
7. Trail-stop policy is "always re-align to current `Sup_N`/`Res_N`,"
   gated by tick-rounded value change.
8. When a held contract's next RTH trading day is on or beyond `last_day`,
   the EOD/break run stages the RTH-open closeout. Equities roll conditionally
   on `ROLL_ENABLED[s]` and `RSpos_N`. Commodities never roll.
9. Order mechanics for the close-and-roll use Quartet's replace-stop OCA
   pattern: cancel the existing stop, place a replacement stop with
   `transmit=False`, then place the `MKT outsideRth=False` exit with
   `transmit=True`. The new entry is a parent/child bracket with a
   `MKT outsideRth=False` parent and an `STP outsideRth=True` child.
10. Execution is fire-and-forget. No per-order ack waits. Idempotency comes
    from the next run's `reqAllOpenOrders` reconcile. A same-session
    `reqAllOpenOrders` refresh is included in the execution report only.
11. Stale-entry cancellation fires the same run a signal disappears.
12. Skip reasons collapse to three: `already_has_position`,
    `already_has_entry_order`, `insufficient_risk_budget`.
13. Deployment in v1 is manual or operator-managed cron. No scheduler ships
    with the package.

## Definition Of Done

The first production-ready version is done when:

```text
the daily flow runs signal + trade in one process with in-memory handoff
held positions and open orders are reconciled before signal-dependent planning
unsafe-attribution states are reported without gating planning
signals become broker-neutral order intents
dry-run and live execution share the same plan model
IBKR code is isolated under broker/ibkr
business logic is covered by tests without an IBKR connection
live execution is idempotent across repeated EOD runs
```
