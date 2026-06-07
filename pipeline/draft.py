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

# Mock-draft scoring: a team's per-pick weight on the BPA (best player
# available) by their positional need at that pick's position.
MOCK_NEED_MULTIPLIER = {"gap": 1.25, "average": 1.0, "surplus": 0.70}


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


def build_mock_draft(
    rookies: list[Player],
    draft_order: dict[int, int],            # {slot: roster_id} — linear order
    draft_rounds: int,
    num_teams: int,
    team_meta: dict[int, dict],
    position_strengths_by_team: dict[int, dict],
) -> list[dict]:
    """Project the rookie draft pick-by-pick. Each team takes the best
    remaining rookie weighted by its own positional needs (gap positions
    boosted, surplus positions discounted). Linear draft — same slot each round.

    Returns a flat list ordered by overall pick:
      [{round, slot, overall, slot_label, roster_id, team_name,
        owner_display_name, player, reasoning}, ...]
    """
    if not draft_order:
        return []
    pool: list[Player] = sorted(rookies, key=lambda p: p.dynasty_value, reverse=True)
    picks: list[dict] = []
    for rnd in range(1, draft_rounds + 1):
        for slot in range(1, num_teams + 1):
            roster_id = draft_order.get(slot)
            if roster_id is None or not pool:
                continue
            needs = position_strengths_by_team.get(roster_id, {})

            def score(p: Player, needs: dict = needs) -> float:
                mult = MOCK_NEED_MULTIPLIER.get(
                    needs.get(p.position, {}).get("label", "average"), 1.0
                )
                return p.dynasty_value * mult

            picked = max(pool, key=score)
            pool.remove(picked)

            info = needs.get(picked.position, {})
            label = info.get("label", "average")
            rank = info.get("league_rank")
            if label == "gap":
                reasoning = f"fills {picked.position} gap (#{rank} of {num_teams})"
            elif label == "surplus":
                reasoning = f"best available despite {picked.position} surplus"
            else:
                reasoning = f"best available ({picked.position})"

            meta = team_meta.get(roster_id, {})
            picks.append({
                "round": rnd,
                "slot": slot,
                "overall": (rnd - 1) * num_teams + slot,
                "slot_label": f"{rnd}.{slot:02d}",
                "roster_id": roster_id,
                "team_name": meta.get("team_name"),
                "owner_display_name": meta.get("owner_display_name"),
                "player": {
                    "sleeper_id": picked.sleeper_id,
                    "name": picked.name,
                    "position": picked.position,
                    "team": picked.team,
                    "age": picked.age,
                    "dynasty_value": picked.dynasty_value,
                    "redraft_value": picked.redraft_value,
                    "injury_status": picked.injury_status,
                },
                "reasoning": reasoning,
            })
    return picks


def build_draft_report(
    available_rookies: list[Player],
    my_slots: list[str],
    season: str,
    num_teams: int,
    pick_slot_values: dict[tuple[str, int, int], int],
    position_strengths_by_team: dict[int, dict] | None = None,
    draft_order: dict[int, int] | None = None,
    team_meta: dict[int, dict] | None = None,
    draft_rounds: int = 3,
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

    mock_draft: list[dict] = []
    if draft_order and team_meta and position_strengths_by_team:
        mock_draft = build_mock_draft(
            rookies=rookies,
            draft_order=draft_order,
            draft_rounds=draft_rounds,
            num_teams=num_teams,
            team_meta=team_meta,
            position_strengths_by_team=position_strengths_by_team,
        )

    return {
        "season": season,
        "num_teams": num_teams,
        "my_slots": slots,
        "later_board": later_board,
        "rookie_pool_size": len(rookies),
        "position_demand": demand,
        "mock_draft": mock_draft,
    }
