"""Make predictions: score processed contracts with each system's model."""

from quintet.make_predictions.clusters import ClusterAssigner
from quintet.make_predictions.predictor import ContractPredictor

__all__ = ["ClusterAssigner", "ContractPredictor"]
