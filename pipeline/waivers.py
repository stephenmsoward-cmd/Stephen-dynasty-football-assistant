"""Waiver-wire recommender.

For a given roster, identifies:
  - Trending Adds — community pickup heat (Sleeper) intersected with what's
    actually available in this league
  - Best Available Overall — top FantasyCalc-valued players not on any roster
  - Targeted at Your Gap Positions — best available at positions where the
    user's lineup is ranked in the bottom third of the league
  - Drop Candidates — the user's lowest-value rostered players

Each pickup gets a suggested drop: the lowest-value rostered player
eligible to be replaced by that pickup (same position or, for skill
players, a worse skill player).
"""
from __future__ import annotations

from dataclasses import dataclass

from data import Player

# Players below this dynasty value aren't worth surfacing as pickups.
MIN_PICKUP_VALUE = 200
TOP_OVERALL = 10
TOP_PER_GAP_POSITION = 5
TOP_TRENDING = 8
TOP_DROPS = 6


@dataclass
class PickupSuggestion:
    pickup: Player
    suggested_drop: Player | None
    value_delta: int  # pickup.dynasty_value - drop.dynasty_value
    trending_count: int | None  # community adds in last 24h, if trending


def _eligible_drop_for(pickup: Player, my_roster: list[Player]) -> Player | None:
    """Lowest-value rostered player the pickup could plausibly replace.
    For skill players: cheapest skill player on the roster (assumes lineup
    flexibility). For K/DEF: cheapest same-position player on the roster.
    Picks are never drop candidates."""
    if pickup.position in {"K", "DEF"}:
        candidates = [p for p in my_roster if p.position == pickup.position]
    elif pickup.is_skill:
        candidates = [p for p in my_roster if p.is_skill]
    else:
        candidates = [p for p in my_roster if p.position not in {"PICK"}]

    candidates = [c for c in candidates if c.dynasty_value < pickup.dynasty_value]
    if not candidates:
        return None
    return min(candidates, key=lambda p: p.dynasty_value)


def build_waiver_report(
    my_roster: list[Player],
    available_players: list[Player],
    trending_adds: dict[str, int],     # {sleeper_id: count}
    gap_positions: list[str],
) -> dict:
    """Returns the waiver payload to attach to the league report."""
    available_by_value = sorted(
        [p for p in available_players if p.dynasty_value >= MIN_PICKUP_VALUE],
        key=lambda p: p.dynasty_value,
        reverse=True,
    )

    def make_suggestion(p: Player) -> PickupSuggestion:
        drop = _eligible_drop_for(p, my_roster)
        return PickupSuggestion(
            pickup=p,
            suggested_drop=drop,
            value_delta=p.dynasty_value - (drop.dynasty_value if drop else 0),
            trending_count=trending_adds.get(p.sleeper_id),
        )

    # Trending: pickups ranked by community count, but only ones available here.
    trending_sorted = sorted(
        [p for p in available_by_value if p.sleeper_id in trending_adds],
        key=lambda p: trending_adds[p.sleeper_id],
        reverse=True,
    )[:TOP_TRENDING]
    trending_section = [make_suggestion(p) for p in trending_sorted]

    # Best available overall.
    best_overall = [make_suggestion(p) for p in available_by_value[:TOP_OVERALL]]

    # Gap-position targeting.
    by_gap_position: dict[str, list[PickupSuggestion]] = {}
    for pos in gap_positions:
        candidates = [p for p in available_by_value if p.position == pos][:TOP_PER_GAP_POSITION]
        if candidates:
            by_gap_position[pos] = [make_suggestion(p) for p in candidates]

    # Drop candidates from my roster — skill players only (K/DEF live in their slots).
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
        "available_count": len(available_by_value),
    }


def _player_to_dict(p: Player) -> dict:
    return {
        "sleeper_id": p.sleeper_id,
        "name": p.name,
        "position": p.position,
        "team": p.team,
        "age": p.age,
        "dynasty_value": p.dynasty_value,
        "redraft_value": p.redraft_value,
        "injury_status": p.injury_status,
    }


def _suggestion_to_dict(s: PickupSuggestion) -> dict:
    return {
        "pickup": _player_to_dict(s.pickup),
        "suggested_drop": _player_to_dict(s.suggested_drop) if s.suggested_drop else None,
        "value_delta": s.value_delta,
        "trending_count": s.trending_count,
    }
