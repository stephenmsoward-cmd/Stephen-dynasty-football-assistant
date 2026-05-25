"""Optimal best-ball lineup calculator.

Given a roster of Players and a list of slot strings from Sleeper (e.g.
['QB','RB','RB','WR','WR','TE','FLEX','FLEX','FLEX','K','DEF']), pick the
lineup that maximizes total value.

Slot semantics in Sleeper:
- 'QB','RB','WR','TE','K','DEF': position-locked
- 'FLEX': RB/WR/TE
- 'SUPER_FLEX' or 'SF': QB/RB/WR/TE
- 'REC_FLEX': WR/TE
- 'BN','TAXI','IR': not starting slots
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from data import Player

ValueFn = Callable[[Player], int]

SLOT_ELIGIBILITY: dict[str, set[str]] = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "DEF": {"DEF"},
    "FLEX": {"RB", "WR", "TE"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "SF": {"QB", "RB", "WR", "TE"},
}

STARTING_SLOTS = set(SLOT_ELIGIBILITY.keys())


@dataclass
class LineupResult:
    assignments: list[tuple[str, Player]]  # (slot, player) in input slot order
    total_value: int

    def by_position(self) -> dict[str, list[Player]]:
        out: dict[str, list[Player]] = {}
        for _, p in self.assignments:
            out.setdefault(p.position, []).append(p)
        return out


def optimal_lineup(
    players: list[Player],
    slots: list[str],
    value_fn: ValueFn = lambda p: p.dynasty_value,
) -> LineupResult:
    """Greedy: assign most-restrictive slots first, then flex slots from the
    remaining pool. Greedy is optimal here because flex is a strict superset
    of the positions it pulls from — there's no scenario where reserving a
    higher-value player for flex beats placing the highest-value player at
    each position-locked slot first.

    value_fn lets callers switch between Dynasty (dynasty_value) and Win-Now
    (redraft_value) modes — the chosen lineup may differ between modes."""
    starting_slots = [s for s in slots if s in STARTING_SLOTS]
    indexed = sorted(
        enumerate(starting_slots),
        key=lambda x: (len(SLOT_ELIGIBILITY[x[1]]), x[0]),
    )

    available = list(players)
    result: list[tuple[str, Player] | None] = [None] * len(starting_slots)

    for original_idx, slot in indexed:
        eligible = [p for p in available if p.position in SLOT_ELIGIBILITY[slot]]
        if not eligible:
            continue
        best = max(eligible, key=value_fn)
        result[original_idx] = (slot, best)
        available.remove(best)

    assignments = [item for item in result if item is not None]
    total = sum(value_fn(p) for _, p in assignments)
    return LineupResult(assignments=assignments, total_value=total)
