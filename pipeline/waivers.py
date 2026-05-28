"""Waiver-wire recommender.

For a given roster, identifies:
  - Trending Adds — community pickup heat (Sleeper), filtered to actually-available players
  - Best Available Overall — top FantasyCalc-valued veterans not on any roster
  - Targeted at Your Gap Positions — best available at positions where your
    lineup ranks in the bottom third of the league
  - Drop Candidates — your lowest-value rostered players

Rookies (years_exp == 0) are filtered out: they belong on the Draft
Recommendations page, not the waiver wire. After the rookie draft completes
and players go undrafted, they'll naturally appear here as veterans.

Each pickup is paired with a short list of suggested drop candidates so the
user has options instead of always the same single name.
"""
from __future__ import annotations

from dataclasses import dataclass

from data import Player

MIN_PICKUP_VALUE = 200
TOP_OVERALL = 5
TOP_PER_GAP_POSITION = 3
TOP_TRENDING = 5
TOP_DROPS = 6
DROPS_PER_PICKUP = 3


def _is_rookie(p: Player) -> bool:
    """Year-zero NFL players. Heuristic uses Sleeper's years_exp."""
    return p.years_exp == 0


@dataclass
class PickupSuggestion:
    pickup: Player
    suggested_drops: list[Player]   # up to DROPS_PER_PICKUP, lowest value first
    trending_count: int | None


def _drop_candidates_for(
    pickup: Player,
    my_roster: list[Player],
    starter_ids: set[str],
) -> list[Player]:
    """Return up to DROPS_PER_PICKUP suggested drop candidates.

    Rules:
    - Never suggest a player in the optimal starting lineup.
    - Only suggest players worth less than the pickup.
    - Prioritize same-position non-starters (drop a QB for a QB), then fall
      back to the lowest-value bench players overall.
    """
    if pickup.position in {"K", "DEF"}:
        pool = [p for p in my_roster if p.position == pickup.position]
    elif pickup.is_skill:
        pool = [p for p in my_roster if p.is_skill]
    else:
        pool = [p for p in my_roster if p.position != "PICK"]

    pool = [
        c for c in pool
        if c.dynasty_value < pickup.dynasty_value and c.sleeper_id not in starter_ids
    ]
    same_pos = sorted(
        [c for c in pool if c.position == pickup.position],
        key=lambda p: p.dynasty_value,
    )
    other = sorted(
        [c for c in pool if c.position != pickup.position],
        key=lambda p: p.dynasty_value,
    )
    return (same_pos + other)[:DROPS_PER_PICKUP]


def build_waiver_report(
    my_roster: list[Player],
    available_players: list[Player],
    trending_adds: dict[str, int],
    gap_positions: list[str],
    starter_ids: set[str] | None = None,
) -> dict:
    """Returns the waiver payload. Rookies are excluded from the pool here
    (they live on the draft page)."""
    starters = starter_ids or set()
    veterans = [p for p in available_players if not _is_rookie(p)]
    pool = sorted(
        [p for p in veterans if p.dynasty_value >= MIN_PICKUP_VALUE],
        key=lambda p: p.dynasty_value,
        reverse=True,
    )

    def make_suggestion(p: Player) -> PickupSuggestion:
        drops = _drop_candidates_for(p, my_roster, starters)
        return PickupSuggestion(
            pickup=p,
            suggested_drops=drops,
            trending_count=trending_adds.get(p.sleeper_id),
        )

    trending_sorted = sorted(
        [p for p in pool if p.sleeper_id in trending_adds],
        key=lambda p: trending_adds[p.sleeper_id],
        reverse=True,
    )[:TOP_TRENDING]
    trending_section = [make_suggestion(p) for p in trending_sorted]

    best_overall = [make_suggestion(p) for p in pool[:TOP_OVERALL]]

    by_gap_position: dict[str, list[PickupSuggestion]] = {}
    for pos in gap_positions:
        candidates = [p for p in pool if p.position == pos][:TOP_PER_GAP_POSITION]
        if candidates:
            by_gap_position[pos] = [make_suggestion(p) for p in candidates]

    drop_pool = [p for p in my_roster if p.is_skill]
    drop_pool.sort(key=lambda p: p.dynasty_value)
    drop_candidates = drop_pool[:TOP_DROPS]

    return {
        "trending": [_suggestion_to_dict(s) for s in trending_section],
        "best_overall": [_suggestion_to_dict(s) for s in best_overall],
        "by_gap_position": {
            pos: [_suggestion_to_dict(s) for s in suggestions]
            for pos, suggestions in by_gap_position.items()
        },
        "drop_candidates": [_player_to_dict(p) for p in drop_candidates],
        "gap_positions": gap_positions,
        "available_count": len(pool),
        "rookies_excluded": len(available_players) - len(veterans),
    }


def _player_to_dict(p: Player) -> dict:
    return {
        "sleeper_id": p.sleeper_id,
        "name": p.name,
        "position": p.position,
        "team": p.team,
        "age": p.age,
        "years_exp": p.years_exp,
        "dynasty_value": p.dynasty_value,
        "redraft_value": p.redraft_value,
        "injury_status": p.injury_status,
    }


def _suggestion_to_dict(s: PickupSuggestion) -> dict:
    return {
        "pickup": _player_to_dict(s.pickup),
        "suggested_drops": [_player_to_dict(p) for p in s.suggested_drops],
        "trending_count": s.trending_count,
    }
