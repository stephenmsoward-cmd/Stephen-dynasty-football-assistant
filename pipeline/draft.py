"""Rookie draft recommendation engine.

For each of the user's owned pick slots, projects which prospects will be
available when they're on the clock. Two boards are produced:

  1. **Strict by-value** — assumes every manager picks purely by FantasyCalc
     dynasty value descending. Easy to reason about but unrealistic.

  2. **Team-need adjusted** — boosts rookies whose position is a gap for
     many teams in the league and discounts rookies at positions where
     many teams already have a surplus. A rough but useful model of how
     positional demand reshapes the board.
"""
from __future__ import annotations

from dataclasses import dataclass

from data import Player

PROSPECTS_PER_SLOT = 8
PROSPECTS_AFTER_LAST_SLOT = 12

# Demand scoring: each position gets a 0..1 demand score from the SPREAD of
# starter values across the league at that position (high spread = more
# variance = more hungry teams). The adjusted-board value multiplier is
# 1 + (demand_score * DEMAND_TUNING).
DEMAND_TUNING = 0.20  # max boost = 20% at demand_score 1.0


def parse_slot(s: str) -> tuple[int, int]:
    """'1.10' or '1.01' → (round, slot_in_round). Slot is 1-indexed."""
    round_str, slot_str = s.split(".")
    return int(round_str), int(slot_str)


def overall_pick(rnd: int, slot_in_round: int, num_teams: int) -> int:
    return (rnd - 1) * num_teams + slot_in_round


def compute_position_demand(
    position_strengths_by_team: dict[int, dict],
) -> dict[str, dict]:
    """Returns per-position demand summary including gap/surplus counts AND
    a normalized demand_score driven by value spread across the league.

    Higher spread = more variance in who has the stars = more teams hungry
    for that position → bigger draft-board boost for that position's rookies.
    """
    # Collect per-position starter values across all teams.
    by_pos_values: dict[str, list[int]] = {}
    by_pos_labels: dict[str, dict[str, int]] = {}
    for strength in position_strengths_by_team.values():
        for pos, info in strength.items():
            by_pos_values.setdefault(pos, []).append(info["value"])
            d = by_pos_labels.setdefault(pos, {"gaps": 0, "surpluses": 0})
            if info["label"] == "gap":
                d["gaps"] += 1
            elif info["label"] == "surplus":
                d["surpluses"] += 1

    # Compute demand score per position from value spread.
    out: dict[str, dict] = {}
    for pos, values in by_pos_values.items():
        if not values:
            continue
        mean = sum(values) / len(values) if values else 1
        spread = (max(values) - min(values)) / mean if mean > 0 else 0
        # Normalize against a typical spread for skill positions (~2.0 maxes out).
        demand_score = min(1.0, spread / 2.0)
        out[pos] = {
            "gaps": by_pos_labels.get(pos, {}).get("gaps", 0),
            "surpluses": by_pos_labels.get(pos, {}).get("surpluses", 0),
            "league_max": max(values),
            "league_min": min(values),
            "league_mean": int(mean),
            "spread_ratio": round(spread, 2),
            "demand_score": round(demand_score, 3),
        }
    return out


def adjusted_dynasty_value(p: Player, demand: dict[str, dict]) -> int:
    """FC dynasty value scaled by league-wide positional demand score."""
    d = demand.get(p.position)
    if not d:
        return p.dynasty_value
    factor = 1 + (d["demand_score"] * DEMAND_TUNING)
    return int(p.dynasty_value * factor)


def _player_dict(p: Player, projected_rank: int, adjusted_value: int | None, demand: dict[str, dict] | None) -> dict:
    d = {
        "sleeper_id": p.sleeper_id,
        "name": p.name,
        "position": p.position,
        "team": p.team,
        "age": p.age,
        "dynasty_value": p.dynasty_value,
        "redraft_value": p.redraft_value,
        "injury_status": p.injury_status,
        "projected_rank": projected_rank,
    }
    if adjusted_value is not None:
        d["adjusted_value"] = adjusted_value
        d["adjusted_delta"] = adjusted_value - p.dynasty_value
    if demand is not None:
        d["pos_demand"] = demand.get(p.position)
    return d


def build_draft_report(
    available_rookies: list[Player],
    my_slots: list[str],
    season: str,
    num_teams: int,
    pick_slot_values: dict[tuple[str, int, int], int],
    position_strengths_by_team: dict[int, dict] | None = None,
) -> dict:
    """Returns the draft payload to attach to the league report."""
    rookies = [r for r in available_rookies if r.dynasty_value > 0]

    # Strict by-value board.
    strict_sorted = sorted(rookies, key=lambda p: p.dynasty_value, reverse=True)

    # Team-need adjusted board.
    demand: dict[str, dict] = {}
    if position_strengths_by_team:
        demand = compute_position_demand(position_strengths_by_team)
    adjusted_sorted = sorted(
        rookies,
        key=lambda p: adjusted_dynasty_value(p, demand),
        reverse=True,
    )

    slots: list[dict] = []
    last_overall = 0
    for slot_label in my_slots:
        rnd, slot_in_round = parse_slot(slot_label)
        overall = overall_pick(rnd, slot_in_round, num_teams)
        last_overall = max(last_overall, overall)
        fc_val = pick_slot_values.get((season, rnd, slot_in_round), 0)

        start = overall - 1
        end = start + PROSPECTS_PER_SLOT

        strict_slice = [
            _player_dict(p, projected_rank=start + i + 1, adjusted_value=None, demand=None)
            for i, p in enumerate(strict_sorted[start:end])
        ]
        adjusted_slice = [
            _player_dict(
                p,
                projected_rank=start + i + 1,
                adjusted_value=adjusted_dynasty_value(p, demand),
                demand=demand,
            )
            for i, p in enumerate(adjusted_sorted[start:end])
        ]

        # Flag movers — players in one board but not the other (in this window).
        strict_ids = {p["sleeper_id"] for p in strict_slice}
        adjusted_ids = {p["sleeper_id"] for p in adjusted_slice}
        for p in adjusted_slice:
            p["new_to_window"] = p["sleeper_id"] not in strict_ids
        for p in strict_slice:
            p["dropped_from_window"] = p["sleeper_id"] not in adjusted_ids

        slots.append({
            "label": slot_label,
            "round": rnd,
            "slot_in_round": slot_in_round,
            "overall": overall,
            "season": season,
            "fc_value": fc_val,
            "projected_strict": strict_slice,
            "projected_adjusted": adjusted_slice,
        })

    later_start = last_overall + PROSPECTS_PER_SLOT - 1
    later_board = [
        _player_dict(
            p,
            projected_rank=later_start + i + 1,
            adjusted_value=adjusted_dynasty_value(p, demand),
            demand=demand,
        )
        for i, p in enumerate(adjusted_sorted[later_start:later_start + PROSPECTS_AFTER_LAST_SLOT])
    ]

    return {
        "season": season,
        "num_teams": num_teams,
        "my_slots": slots,
        "later_board": later_board,
        "rookie_pool_size": len(rookies),
        "position_demand": demand,
    }
