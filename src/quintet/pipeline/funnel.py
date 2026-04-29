"""Funnel state for the daily pipeline.

The funnel is the per-system per-product state that filter stages mutate.
Each `ProductCandidate` carries its full diagnostic record: prob, cluster
id, structure levels, latest-bar high, plus per-gate pass/fail verdicts.
A product is `actionable` when every gate has passed.

Funnel state is held in `PipelineContext.funnels` for the duration of one
run and snapshotted to `data/processed/_funnel.json` by `SnapshotStage`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ProductCandidate:
    """One product's state through the daily pipeline funnel.

    Diagnostic fields (`prob`, `cluster_id`, `res_n`, `sup_n`, `high`)
    are populated by the build stage. Gate verdicts
    (`tau_pass`, `cluster_pass`, `breakout_pass`) are populated by their
    respective filter stages — `None` means "not yet evaluated."
    """

    product: str
    local_symbol: str
    con_id: int

    # Populated by BuildFunnelStage from the contract's processed parquet.
    prob: float | None = None
    cluster_id: int | None = None
    res_n: float | None = None
    sup_n: float | None = None
    high: float | None = None

    # Populated by the corresponding filter stage; None until that stage runs.
    tau_pass: bool | None = None
    cluster_pass: bool | None = None
    breakout_pass: bool | None = None
    position_pass: bool | None = None

    @property
    def actionable(self) -> bool:
        """True iff every gate has run and produced a True verdict."""
        return (
            self.tau_pass is True
            and self.cluster_pass is True
            and self.breakout_pass is True
            and self.position_pass is True
        )

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "local_symbol": self.local_symbol,
            "con_id": self.con_id,
            "prob": self.prob,
            "cluster_id": self.cluster_id,
            "res_n": self.res_n,
            "sup_n": self.sup_n,
            "high": self.high,
            "tau_pass": self.tau_pass,
            "cluster_pass": self.cluster_pass,
            "breakout_pass": self.breakout_pass,
            "position_pass": self.position_pass,
            "actionable": self.actionable,
        }


@dataclass
class SystemFunnel:
    """Per-system funnel state for one pipeline run."""

    system: str
    today: date
    products: dict[str, ProductCandidate] = field(default_factory=dict)
    tau: float | None = None  # set by TauStage

    @property
    def actionable_products(self) -> list[ProductCandidate]:
        return [p for p in self.products.values() if p.actionable]

    def count_passing(self, gate: str) -> int:
        """Count products where `<gate>_pass is True`. `gate` ∈
        {tau, cluster, breakout, position}."""
        attr = f"{gate}_pass"
        return sum(1 for p in self.products.values() if getattr(p, attr) is True)

    def count_surviving_through(self, *gates: str) -> int:
        """Count products where every named gate has produced `True`.
        Useful for "running funnel size after this stage."
        """
        attrs = [f"{g}_pass" for g in gates]
        return sum(
            1
            for p in self.products.values()
            if all(getattr(p, a) is True for a in attrs)
        )

    def to_dict(self) -> dict:
        return {
            "system": self.system,
            "today": str(self.today),
            "tau": self.tau,
            "n_universe": len(self.products),
            "n_tau_pass": self.count_passing("tau"),
            "n_cluster_pass": self.count_passing("cluster"),
            "n_breakout_pass": self.count_passing("breakout"),
            "n_position_pass": self.count_passing("position"),
            "n_actionable": len(self.actionable_products),
            "products": [p.to_dict() for p in self.products.values()],
        }
