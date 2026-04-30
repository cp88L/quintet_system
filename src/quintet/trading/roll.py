"""Planner-only roll-entry reporting."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from quintet.config import ROLL_ENABLED, ROLL_RSPOS_MIN
from quintet.execution.models import (
    AlertIntent,
    AlertLevel,
    ExitPositionIntent,
    RollEntryIntent,
)
from quintet.trading.models import Side


@dataclass(frozen=True)
class RollCandidate:
    """Current candidate contract used to decide conditional roll entry."""

    system: str
    side: Side
    symbol: str
    local_symbol: str
    con_id: int
    exchange: str
    currency: str
    rspos: float | None
    stop_price: float | None


def plan_roll_entries(
    maintenance_intents: Iterable[object],
    candidates: Mapping[tuple[str, str], RollCandidate],
) -> list[object]:
    """Build report-only roll-entry intents for last-day exits."""
    intents: list[object] = []
    for intent in maintenance_intents:
        if not isinstance(intent, ExitPositionIntent):
            continue
        if intent.reason != "last_day":
            continue

        system = intent.key[1]
        if not ROLL_ENABLED.get(system, False):
            continue

        candidate = candidates.get((system, intent.symbol))
        if candidate is None:
            intents.append(
                AlertIntent(
                    code="roll_candidate_missing",
                    message=f"{intent.symbol} has no roll candidate for {system}",
                    key=intent.key,
                )
            )
            continue
        if candidate.con_id == intent.key[0]:
            intents.append(
                AlertIntent(
                    code="roll_contract_not_advanced",
                    message=(
                        f"{intent.symbol} roll candidate is still "
                        f"{intent.local_symbol}"
                    ),
                    key=intent.key,
                )
            )
            continue
        if candidate.rspos is None:
            intents.append(
                AlertIntent(
                    code="roll_rspos_missing",
                    message=f"{candidate.local_symbol} has no RSpos for roll entry",
                    key=intent.key,
                )
            )
            continue

        threshold = ROLL_RSPOS_MIN[system]
        if candidate.rspos < threshold:
            intents.append(
                AlertIntent(
                    code="roll_not_eligible",
                    message=(
                        f"{candidate.local_symbol} RSpos {candidate.rspos:.4f} "
                        f"is below roll threshold {threshold:.4f}"
                    ),
                    key=intent.key,
                    level=AlertLevel.INFO,
                )
            )
            continue
        if candidate.stop_price is None:
            intents.append(
                AlertIntent(
                    code="roll_stop_missing",
                    message=f"{candidate.local_symbol} has no roll stop price",
                    key=intent.key,
                )
            )
            continue

        intents.append(
            RollEntryIntent(
                old_key=intent.key,
                new_key=(candidate.con_id, system),
                side=candidate.side,
                symbol=candidate.symbol,
                old_local_symbol=intent.local_symbol,
                new_local_symbol=candidate.local_symbol,
                exchange=candidate.exchange,
                currency=candidate.currency,
                quantity=intent.quantity,
                rspos=candidate.rspos,
                threshold=threshold,
                protective_stop_price=candidate.stop_price,
            )
        )
    return intents
