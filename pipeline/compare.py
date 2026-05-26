"""Team comparison.

Produces side-by-side full roster comparisons between your team and each
opposing team. Players are grouped by position and sorted within each
group by dynasty value descending. Per-position totals and a winner
indicator surface mismatches at a glance.
"""
from __future__ import annotations

from data import Player

POSITIONS_TO_COMPARE = ["QB", "RB", "WR", "TE"]


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


def _group_by_position(players: list[Player]) -> dict[str, list[dict]]:
    """Return {position: [player_dict sorted by dynasty value desc]}."""
    by_pos: dict[str, list[Player]] = {}
    for p in players:
        if p.position in POSITIONS_TO_COMPARE:
            by_pos.setdefault(p.position, []).append(p)
    out: dict[str, list[dict]] = {}
    for pos in POSITIONS_TO_COMPARE:
        ps = sorted(by_pos.get(pos, []), key=lambda x: x.dynasty_value, reverse=True)
        out[pos] = [_player_dict(p) for p in ps]
    return out


def _position_totals(by_pos: dict[str, list[dict]]) -> dict[str, int]:
    return {pos: sum(p["dynasty_value"] for p in players) for pos, players in by_pos.items()}


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


def build_compare_report(
    my_roster_id: int,
    rostered_by_team: dict[int, list[Player]],
    picks_by_team: dict[int, list[Player]],
    teams_data: list[dict],
    team_meta: dict[int, dict],
) -> dict:
    """Returns the compare payload: my team's roster + one comparison entry
    per opposing team."""
    my_players = rostered_by_team[my_roster_id]
    my_picks = picks_by_team.get(my_roster_id, [])
    my_by_pos = _group_by_position(my_players)
    my_totals = _position_totals(my_by_pos)
    my_team_record = next(t for t in teams_data if t["roster_id"] == my_roster_id)

    comparisons: list[dict] = []
    for rid, players in rostered_by_team.items():
        if rid == my_roster_id:
            continue
        their_meta = team_meta[rid]
        their_picks = picks_by_team.get(rid, [])
        their_by_pos = _group_by_position(players)
        their_totals = _position_totals(their_by_pos)
        their_record = next(t for t in teams_data if t["roster_id"] == rid)

        position_diffs = {
            pos: my_totals.get(pos, 0) - their_totals.get(pos, 0)
            for pos in POSITIONS_TO_COMPARE
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
            "total_my_assets": sum(my_totals.values()) + sum(p.dynasty_value for p in my_picks),
            "total_their_assets": sum(their_totals.values()) + sum(p.dynasty_value for p in their_picks),
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
