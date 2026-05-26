"""League power rankings.

Combines dynasty starter value, win-now starter value, and total dynasty
asset value (including picks) into a single composite rank per team.
Assigns a trajectory label based on the spread between dynasty and
win-now ranks.
"""
from __future__ import annotations

from data import Player

# When dynasty_rank and winnow_rank differ by more than this many slots,
# the team gets a directional trajectory label.
TRAJECTORY_THRESHOLD = 2


def _trajectory(dynasty_rank: int, winnow_rank: int) -> str:
    delta = dynasty_rank - winnow_rank
    # delta > 0 means dynasty rank is worse (higher number) than win-now rank
    # → team is better in win-now mode → "Win-Now"
    if delta > TRAJECTORY_THRESHOLD:
        return "win-now"
    if delta < -TRAJECTORY_THRESHOLD:
        return "rebuild"
    return "balanced"


def build_power_rankings(
    teams_data: list[dict],
    rostered_by_team: dict[int, list[Player]],
    picks_by_team: dict[int, list[Player]],
) -> dict:
    """Returns the rankings payload. Asset value includes ALL rostered players
    plus pick values — captures depth, not just starting lineup."""
    rows: list[dict] = []
    for t in teams_data:
        rid = t["roster_id"]
        players = rostered_by_team.get(rid, [])
        picks = picks_by_team.get(rid, [])
        asset_value = sum(p.dynasty_value for p in players) + sum(p.dynasty_value for p in picks)

        rows.append({
            "roster_id": rid,
            "team_name": t["team_name"],
            "owner_display_name": t["owner_display_name"],
            "dynasty_rank": t["modes"]["dynasty"]["rank"],
            "winnow_rank": t["modes"]["winnow"]["rank"],
            "dynasty_total": t["modes"]["dynasty"]["total_value"],
            "winnow_total": t["modes"]["winnow"]["total_value"],
            "asset_value": asset_value,
            "player_count": len(players),
            "pick_count": len(picks),
            "pick_value": sum(p.dynasty_value for p in picks),
        })

    # Asset rank.
    rows.sort(key=lambda r: r["asset_value"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["asset_rank"] = i

    # Composite: average of dynasty_rank, winnow_rank, asset_rank.
    for r in rows:
        r["composite_score"] = (r["dynasty_rank"] + r["winnow_rank"] + r["asset_rank"]) / 3
        r["trajectory"] = _trajectory(r["dynasty_rank"], r["winnow_rank"])

    # Composite rank (lower composite score = better).
    rows.sort(key=lambda r: r["composite_score"])
    for i, r in enumerate(rows, 1):
        r["composite_rank"] = i

    # Reference maxes for the bar visualization.
    max_dynasty = max(r["dynasty_total"] for r in rows) if rows else 1
    max_winnow = max(r["winnow_total"] for r in rows) if rows else 1
    max_asset = max(r["asset_value"] for r in rows) if rows else 1

    for r in rows:
        r["dynasty_bar_pct"] = round(100 * r["dynasty_total"] / max_dynasty) if max_dynasty else 0
        r["winnow_bar_pct"] = round(100 * r["winnow_total"] / max_winnow) if max_winnow else 0
        r["asset_bar_pct"] = round(100 * r["asset_value"] / max_asset) if max_asset else 0

    return {
        "rows": rows,
        "max_dynasty": max_dynasty,
        "max_winnow": max_winnow,
        "max_asset": max_asset,
    }
