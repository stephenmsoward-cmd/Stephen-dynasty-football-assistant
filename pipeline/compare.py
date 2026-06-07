"""Team comparison.

Produces side-by-side full-roster comparisons between your team and each
opposing team. Computed under both Dynasty and Win-Now value modes — within
each position, the list is sorted by the active mode's value, and totals /
diffs are mode-specific. Picks count only in dynasty (they're future capital).
"""
from __future__ import annotations

from data import Player

POSITIONS_TO_COMPARE = ["QB", "RB", "WR", "TE"]
MODES = ("dynasty", "winnow")


def _player_dict(p: Player) -> dict:
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


def _value_key(mode: str):
    return (lambda p: p.dynasty_value) if mode == "dynasty" else (lambda p: p.redraft_value)


def _group_by_position_modes(players: list[Player]) -> dict[str, dict[str, list[dict]]]:
    """{mode: {pos: [player_dict sorted desc by that mode's value]}}."""
    by_pos: dict[str, list[Player]] = {}
    for p in players:
        if p.position in POSITIONS_TO_COMPARE:
            by_pos.setdefault(p.position, []).append(p)
    out: dict[str, dict[str, list[dict]]] = {}
    for mode in MODES:
        vf = _value_key(mode)
        out[mode] = {
            pos: [_player_dict(p) for p in sorted(by_pos.get(pos, []), key=vf, reverse=True)]
            for pos in POSITIONS_TO_COMPARE
        }
    return out


def _position_totals_modes(players: list[Player]) -> dict[str, dict[str, int]]:
    """{mode: {pos: sum of that mode's values across all rostered players}}."""
    out: dict[str, dict[str, int]] = {
        m: {pos: 0 for pos in POSITIONS_TO_COMPARE} for m in MODES
    }
    for p in players:
        if p.position not in POSITIONS_TO_COMPARE:
            continue
        out["dynasty"][p.position] += p.dynasty_value
        out["winnow"][p.position] += p.redraft_value
    return out


def _pick_summary(picks: list[Player]) -> dict:
    return {
        "count": len(picks),
        "total_value": sum(p.dynasty_value for p in picks),
        "picks": sorted(
            [_player_dict(p) for p in picks],
            key=lambda d: d["dynasty_value"],
            reverse=True,
        ),
    }


def _total_assets(totals: dict[str, dict[str, int]], pick_value: int) -> dict[str, int]:
    """Aggregate header value per mode. Picks are future capital → dynasty only."""
    return {
        "dynasty": sum(totals["dynasty"].values()) + pick_value,
        "winnow": sum(totals["winnow"].values()),
    }


def build_compare_report(
    my_roster_id: int,
    rostered_by_team: dict[int, list[Player]],
    picks_by_team: dict[int, list[Player]],
    teams_data: list[dict],
    team_meta: dict[int, dict],
) -> dict:
    """Side-by-side comparisons against every opposing team, in both modes."""
    my_players = rostered_by_team[my_roster_id]
    my_picks = picks_by_team.get(my_roster_id, [])
    my_by_pos = _group_by_position_modes(my_players)
    my_totals = _position_totals_modes(my_players)
    my_pick_value = sum(p.dynasty_value for p in my_picks)
    my_total_assets = _total_assets(my_totals, my_pick_value)
    my_team_record = next(t for t in teams_data if t["roster_id"] == my_roster_id)

    comparisons: list[dict] = []
    for rid, players in rostered_by_team.items():
        if rid == my_roster_id:
            continue
        their_meta = team_meta[rid]
        their_picks = picks_by_team.get(rid, [])
        their_by_pos = _group_by_position_modes(players)
        their_totals = _position_totals_modes(players)
        their_pick_value = sum(p.dynasty_value for p in their_picks)
        their_record = next(t for t in teams_data if t["roster_id"] == rid)

        position_diffs = {
            mode: {
                pos: my_totals[mode][pos] - their_totals[mode][pos]
                for pos in POSITIONS_TO_COMPARE
            }
            for mode in MODES
        }

        comparisons.append({
            "partner": {
                **their_meta,
                "dynasty_rank": their_record["modes"]["dynasty"]["rank"],
                "winnow_rank": their_record["modes"]["winnow"]["rank"],
            },
            "their_by_position": their_by_pos,
            "their_totals": their_totals,
            "their_picks": _pick_summary(their_picks),
            "position_diffs": position_diffs,
            "total_my_assets": my_total_assets,
            "total_their_assets": _total_assets(their_totals, their_pick_value),
        })

    comparisons.sort(key=lambda c: c["partner"]["dynasty_rank"])

    return {
        "my_team": {
            **team_meta[my_roster_id],
            "dynasty_rank": my_team_record["modes"]["dynasty"]["rank"],
            "winnow_rank": my_team_record["modes"]["winnow"]["rank"],
        },
        "my_by_position": my_by_pos,
        "my_totals": my_totals,
        "my_picks": _pick_summary(my_picks),
        "comparisons": comparisons,
    }
