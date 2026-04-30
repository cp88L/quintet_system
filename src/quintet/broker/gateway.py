"""Broker gateway protocol used by flows and executors."""

from __future__ import annotations

from typing import Protocol

from quintet.broker.models import BrokerState


class BrokerGateway(Protocol):
    """Minimal broker-facing interface for one daily trade-flow run."""

    def collect_state(self) -> BrokerState:
        """Collect the current broker/account state."""
