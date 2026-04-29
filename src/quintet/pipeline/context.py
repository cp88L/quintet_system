"""Pipeline-wide context shared across stages.

Holds inputs (today, args, registry, paths, master, processors) and
mutable run state (funnels, tau_results). Stages read what they need
and write into the funnels / tau_results dicts.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from quintet.contract_handler.contract_registry import ContractRegistry
from quintet.contract_handler.product_master import ProductMaster
from quintet.data.paths import DataPaths
from quintet.make_predictions import ClusterAssigner, ContractPredictor
from quintet.pipeline.funnel import SystemFunnel
from quintet.process_contracts import ContractProcessor


@dataclass
class PipelineContext:
    today: date
    args: argparse.Namespace
    paths: DataPaths
    registry: ContractRegistry
    master: ProductMaster
    processor: ContractProcessor
    predictor: ContractPredictor
    assigner: ClusterAssigner

    scope: Optional[set[str]] = None  # active-today local symbols, or None for full year
    asof: Optional[date] = None  # trim-today cutoff if set

    funnels: dict[str, SystemFunnel] = field(default_factory=dict)
    tau_results: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def build(cls, args: argparse.Namespace) -> "PipelineContext":
        paths = DataPaths()
        registry = ContractRegistry(paths.contracts_json)
        registry.load()

        processor = ContractProcessor()
        master = processor.master
        predictor = ContractPredictor(master=master)
        assigner = ClusterAssigner(master=master, registry=registry)

        today = date.today()
        asof = today if getattr(args, "trim_today", False) else None

        return cls(
            today=today,
            args=args,
            paths=paths,
            registry=registry,
            master=master,
            processor=processor,
            predictor=predictor,
            assigner=assigner,
            scope=None,  # filled in after registry-driven scope build
            asof=asof,
        )
