"""Daily trade-flow helpers layered after the existing signal pipeline."""

from __future__ import annotations

import pandas as pd

from quintet.broker.ibkr.state import IbkrStateClient
from quintet.broker.models import BrokerState, ContractMeta
from quintet.execution.dry_run import DryRunExecutor
from quintet.execution.ibkr import IbkrExecutor
from quintet.execution.models import ExecutionReport
from quintet.state.stores import ReportStore
from quintet.trading.exposure import RiskMetadata, build_risk_exposures
from quintet.trading.maintain import plan_maintenance
from quintet.trading.models import RiskState, TradePlan
from quintet.trading.planner import build_trade_plan
from quintet.trading.reconcile import reconcile_state
from quintet.trading.risk import build_risk_state
from quintet.trading.signals import candidates_from_context


def plan_trade_flow(ctx, broker_state: BrokerState) -> TradePlan:
    """Build the broker-neutral trade plan from current broker state."""
    reconciled = reconcile_state(broker_state)
    contract_meta = contract_meta_from_context(ctx, reconciled)
    maintenance = plan_maintenance(
        reconciled,
        today=ctx.today,
        contract_meta=contract_meta,
    )
    signals = candidates_from_context(ctx)
    risk_state = risk_state_from_context(ctx, broker_state, reconciled)
    return build_trade_plan(
        signals=signals,
        state=reconciled,
        maintenance=maintenance,
        risk_state=risk_state,
    )


def run_trade_dry_run(
    ctx,
    *,
    broker_state: BrokerState,
) -> tuple[TradePlan, ExecutionReport]:
    """Run broker-neutral trade planning without broker side effects."""
    plan = plan_trade_flow(ctx, broker_state)
    report = DryRunExecutor().execute(plan)
    write_trade_reports(ctx, plan, report)
    return plan, report


def run_trade_live(
    ctx,
) -> tuple[BrokerState, TradePlan, ExecutionReport]:
    """Collect state, plan, and submit supported intents using one IBKR session."""
    client = IbkrStateClient()
    client.connect_and_run()
    try:
        broker_state = client.collect_state()
        plan = plan_trade_flow(ctx, broker_state)
        report = IbkrExecutor().execute_connected(plan, client)
        write_trade_reports(ctx, plan, report)
        return broker_state, plan, report
    finally:
        client.disconnect_and_stop()


def risk_state_from_context(ctx, broker_state: BrokerState, reconciled) -> RiskState:
    """Build pooled risk state from reconciled positions and processed closes."""
    current_prices = {}
    metadata = {}
    for key, position in reconciled.positions_by_key.items():
        system = key[1]
        product = ctx.master.get_product(position.symbol)
        if product is None:
            raise ValueError(f"Missing product config for {position.symbol}")
        current_prices[key] = _latest_processed_close(
            ctx,
            system=system,
            symbol=position.symbol,
            local_symbol=position.local_symbol,
        )
        metadata[key] = RiskMetadata(
            multiplier=product.multiplier,
            price_magnifier=product.price_magnifier,
        )

    exposures = build_risk_exposures(
        reconciled,
        current_prices=current_prices,
        metadata=metadata,
    )
    return build_risk_state(
        account_equity=broker_state.account.net_liquidation,
        positions=exposures,
    )


def contract_meta_from_context(ctx, reconciled) -> dict[int, ContractMeta]:
    """Build contract metadata for currently reconciled positions."""
    meta: dict[int, ContractMeta] = {}
    for position in reconciled.positions_by_key.values():
        contract = ctx.registry.get_contract_by_con_id(position.con_id)
        product = ctx.master.get_product(position.symbol)
        if contract is None or product is None:
            continue
        meta[position.con_id] = ContractMeta(
            con_id=position.con_id,
            symbol=position.symbol,
            local_symbol=position.local_symbol,
            exchange=contract.exchange or product.exchange,
            currency=product.currency,
            multiplier=product.multiplier,
            min_tick=product.min_tick,
            price_magnifier=product.price_magnifier,
            last_trade_date=contract.last_trade_date,
            last_day=contract.scan_window.last_day,
        )
    return meta


def _latest_processed_close(ctx, *, system: str, symbol: str, local_symbol: str) -> float:
    path = ctx.paths.processed / system / symbol / f"{local_symbol}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing processed price data for {system}/{local_symbol}")
    df = pd.read_parquet(path, columns=["close"])
    if df.empty:
        raise ValueError(f"Processed price data is empty for {system}/{local_symbol}")
    return float(df.iloc[-1]["close"])


def write_trade_reports(ctx, plan: TradePlan, report: ExecutionReport) -> None:
    """Write latest trade-flow artifacts for dashboard/operator inspection."""
    store = ReportStore(ctx.paths.base / "reports")
    store.write_trade_plan(plan)
    store.write_execution_report(report)
