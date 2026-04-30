"""Pipeline stages.

Each stage subclasses `PipelineStage` and runs in a fixed order from
`pipeline.stages.PIPELINE`. The order encodes the funnel:

    Fetch → Indicators → Predictions → BuildFunnel → Tau → Cluster
        → Breakout → Snapshot
"""

from quintet.pipeline.stages.base import PipelineStage
from quintet.pipeline.stages.breakout import BreakoutStage
from quintet.pipeline.stages.build_funnel import BuildFunnelStage
from quintet.pipeline.stages.clusters import ClusterStage
from quintet.pipeline.stages.fetch import FetchStage
from quintet.pipeline.stages.indicators import IndicatorsStage
from quintet.pipeline.stages.predictions import PredictionsStage
from quintet.pipeline.stages.snapshot import SnapshotStage
from quintet.pipeline.stages.tau import TauStage


PIPELINE: list[PipelineStage] = [
    FetchStage(),
    IndicatorsStage(),
    PredictionsStage(),
    BuildFunnelStage(),
    TauStage(),
    ClusterStage(),
    BreakoutStage(),
    SnapshotStage(),
]


__all__ = [
    "PIPELINE",
    "PipelineStage",
    "FetchStage",
    "IndicatorsStage",
    "PredictionsStage",
    "BuildFunnelStage",
    "TauStage",
    "ClusterStage",
    "BreakoutStage",
    "SnapshotStage",
]
