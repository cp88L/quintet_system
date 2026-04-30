"""Convert in-memory pipeline funnels into trade signal candidates."""

from __future__ import annotations

from quintet.config import SYSTEM_SIDE
from quintet.pipeline.context import PipelineContext
from quintet.trading.models import Side, SignalCandidate


def candidates_from_context(ctx: PipelineContext) -> list[SignalCandidate]:
    """Build trade candidates from `ctx.funnels` without reading `_funnel.json`."""
    candidates: list[SignalCandidate] = []
    for system, funnel in ctx.funnels.items():
        side = Side.from_config(SYSTEM_SIDE[system])
        for product, p in funnel.products.items():
            if not _passes_signal_gates(p):
                continue
            if p.sup_n is None or p.res_n is None:
                continue

            product_config = ctx.master.get_product(product)
            contract = ctx.registry.get_contract_by_con_id(p.con_id)
            if product_config is None or contract is None:
                continue

            if side is Side.LONG:
                entry_price = p.res_n
                stop_price = p.sup_n
            else:
                entry_price = p.sup_n
                stop_price = p.res_n

            candidates.append(
                SignalCandidate(
                    system=system,
                    side=side,
                    symbol=product,
                    local_symbol=p.local_symbol,
                    con_id=p.con_id,
                    exchange=contract.exchange or product_config.exchange,
                    currency=product_config.currency,
                    multiplier=product_config.multiplier,
                    min_tick=product_config.min_tick,
                    price_magnifier=product_config.price_magnifier,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    prob=p.prob,
                    tau=funnel.tau,
                    cluster_id=p.cluster_id,
                    high=p.high,
                    rspos=p.rspos_n,
                    last_day=contract.scan_window.last_day,
                    contract_month=contract.contract_month,
                )
            )
    return candidates


def _passes_signal_gates(candidate) -> bool:
    return (
        candidate.tau_pass is True
        and candidate.cluster_pass is True
        and candidate.breakout_pass is True
    )
