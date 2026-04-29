"""Position tracker — currently a stub.

Loads `(con_id, system)` keys from `data/positions.json` if the file
exists; returns an empty set otherwise. The funnel's PositionStage
queries `is_held(con_id, system)` to gate new entries.

To wire IBKR: replace `load()` with a `reqPositions` round-trip via a
local `EClient` / `EWrapper` subclass and populate `_held` with one
entry per (con_id, originating system) pair. The originating system
attribution depends on tagging orders with the system name when they
are placed (e.g. via `order.orderRef = "C4"`); position-only data from
IBKR carries no such tag.

JSON shape:

    {
      "positions": [
        {"con_id": 12345, "system": "C4", "local_symbol": "GCM6"},
        ...
      ]
    }

`local_symbol` is informational; only `(con_id, system)` keys the gate.
"""

from __future__ import annotations

import json
from pathlib import Path


class PositionTracker:
    """Tracks held `(con_id, system)` pairs for funnel position-gating."""

    def __init__(self, positions_path: Path | str):
        self.path = Path(positions_path)
        self._held: set[tuple[int, str]] = set()
        self._loaded = False

    def load(self) -> None:
        """Load held positions from JSON. No-op if the file is absent."""
        self._loaded = True
        self._held = set()
        if not self.path.exists():
            return
        with open(self.path) as f:
            data = json.load(f)
        for entry in data.get("positions", []):
            con_id = int(entry["con_id"])
            system = str(entry["system"])
            self._held.add((con_id, system))

    def is_held(self, con_id: int, system: str) -> bool:
        return (con_id, system) in self._held

    def __len__(self) -> int:
        return len(self._held)

    @property
    def is_stub(self) -> bool:
        """True iff nothing has been loaded from disk (no positions file)."""
        return self._loaded and not self.path.exists()
