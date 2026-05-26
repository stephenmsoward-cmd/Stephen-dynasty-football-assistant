"""Rookie draft recommendation engine.

For each of the user's owned pick slots, project which top rookies will likely
be available at that pick and surface a ranked board.

Availability model: strict best-player-available. We assume every manager
drafts purely by FantasyCalc dynasty value descending. Real drafts have
positional runs, reaches, and personal preferences, so treat the projected
board as guidance, not gospel.
"""
from __future__ import annotations

from dataclasses import dataclass

from data import Player

# Number of prospects to show per pick slot (the player at exactly overall_pick
# plus the next N-1 in case earlier ones get sniped).
PROSPECTS_PER_SLOT = 8

# Beyond your last pick — a peek at who'd fall further if it matters for
# trade-up / trade-back decisions.
PROSPECTS_AFTER_LAST_SLOT = 12


def parse_slot(s: str) -> tuple[int, int]:
    """'1.10' or '1.01' → (round, slot_in_round). Slot is 1-indexed."""
    round_str, slot_str = s.split(".")
    return int(round_str), int(slot_str)


def overall_pick(rnd: int, slot_in_round: int, num_teams: int) -> int:
    return (rnd - 1) * num_teams + slot_in_round


def _player_dict(p: Player, projected_rank: int) -> dict:
    return {
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


def build_draft_report(
    available_rookies: list[Player],
    my_slots: list[str],
    season: str,
    num_teams: int,
    pick_slot_values: dict[tuple[str, int, int], int],
) -> dict:
    """Returns the draft payload to attach to the league report."""
    rookies_sorted = sorted(
        [r for r in available_rookies if r.dynasty_value > 0],
        key=lambda p: p.dynasty_value,
        reverse=True,
    )

    slots: list[dict] = []
    last_overall = 0
    for slot_label in my_slots:
        rnd, slot_in_round = parse_slot(slot_label)
        overall = overall_pick(rnd, slot_in_round, num_teams)
        last_overall = max(last_overall, overall)
        fc_val = pick_slot_values.get((season, rnd, slot_in_round), 0)

        # Projected available: rookies starting at the overall pick index.
        start = overall - 1
        end = start + PROSPECTS_PER_SLOT
        available = [
            _player_dict(p, projected_rank=start + i + 1)
            for i, p in enumerate(rookies_sorted[start:end])
        ]

        slots.append({
            "label": slot_label,
            "round": rnd,
            "slot_in_round": slot_in_round,
            "overall": overall,
            "season": season,
            "fc_value": fc_val,
            "projected_available": available,
        })

    # Show the next chunk of prospects falling below your last pick — useful
    # context for trade-back or "should I move up?" decisions.
    later_start = last_overall + PROSPECTS_PER_SLOT - 1
    later_board = [
        _player_dict(p, projected_rank=later_start + i + 1)
        for i, p in enumerate(rookies_sorted[later_start:later_start + PROSPECTS_AFTER_LAST_SLOT])
    ]

    return {
        "season": season,
        "num_teams": num_teams,
        "my_slots": slots,
        "later_board": later_board,
        "rookie_pool_size": len(rookies_sorted),
    }
