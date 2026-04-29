"""Pipeline stage abstract base.

Each stage has a stable name (used for logging and skip-flag matching),
a `run(ctx)` that does the work, and a `skip(args)` predicate that decides
whether to skip this stage based on CLI flags. The default `skip` is
False; stages override when they have a corresponding flag.

`run` should print its own header and per-system summary inline; we don't
separate compute from print because the existing pipeline doesn't, and
mixing the two keeps stages self-contained.
"""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod

from quintet.pipeline.context import PipelineContext


class PipelineStage(ABC):
    """One step of the daily pipeline."""

    name: str = ""  # subclasses override

    @abstractmethod
    def run(self, ctx: PipelineContext) -> None:
        """Do the stage's work, mutating ctx as needed."""

    def skip(self, args: argparse.Namespace) -> bool:
        """Whether to skip this stage given CLI flags. Default: never skip."""
        return False

    def skip_message(self) -> str:
        """Header to print when skipped. Override for custom messages."""
        return f"{self.name} (skipped)"
