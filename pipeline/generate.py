"""Build the static dynasty-tools site.

Reads leagues.yml, pulls fresh data, runs the optimal-lineup calculation under
both Dynasty and Win-Now (redraft) value modes, and emits:
  site/index.html                      — landing page listing leagues
  site/leagues/<slug>/index.html       — per-league best-ball report
  site/leagues/<slug>/data.json        — raw report data
  history/<slug>/YYYY-MM-DD.json       — daily snapshot, git-tracked

Run: python3 pipeline/generate.py
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

import data
from data import Player
from lineup import optimal_lineup
from trades import TradeCandidate, find_trades
from waivers import build_waiver_report

ROOT = Path(__file__).parent.parent
SITE = ROOT / "site"
HISTORY = ROOT / "history"
LEAGUES_CFG = ROOT / "leagues.yml"
TEMPLATES = Path(__file__).parent / "templates"

POS_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF"]
SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]
MODES = ["dynasty", "winnow"]
BENCH_DEPTH = 3
TOP_TRADES_PER_TEAM = 5
TOP_TRADES_PER_TIER = 8
TRADE_MODE = "dynasty"  # Trade analysis uses dynasty value as canonical currency.
PICK_SEASONS_AHEAD = 2  # Include picks for the next N upcoming drafts.


def team_name(user: dict) -> str:
    return user.get("metadata", {}).get("team_name") or user.get("display_name") or "?"


def owner_avatar(user: dict) -> str | None:
    meta = user.get("metadata") or {}
    if meta.get("avatar", "").startswith("http"):
        return meta["avatar"]
    if user.get("avatar"):
        return f"https://sleepercdn.com/avatars/thumbs/{user['avatar']}"
    return None


def value_fn_for(mode: str):
    return (lambda p: p.redraft_value) if mode == "winnow" else (lambda p: p.dynasty_value)


def compute_league_pos_ranks(
    rostered_by_team: dict[int, list[Player]],
    mode: str,
) -> dict[str, int]:
    """Rank every rostered player against every other rostered player at the
    same position across the whole league. Returns {sleeper_id: pos_rank}."""
    by_pos: dict[str, list[Player]] = {}
    for players in rostered_by_team.values():
        for p in players:
            by_pos.setdefault(p.position, []).append(p)
    vf = value_fn_for(mode)
    ranks: dict[str, int] = {}
    for pos, players in by_pos.items():
        players.sort(key=vf, reverse=True)
        for i, p in enumerate(players, 1):
            ranks[p.sleeper_id] = i
    return ranks


def player_to_dict(p: Player, slot: str | None, value_in_mode: int, pos_rank: int | None) -> dict:
    d = {k: v for k, v in asdict(p).items()}
    d["slot"] = slot
    d["value_in_mode"] = value_in_mode
    d["pos_rank_in_league"] = pos_rank
    return d


def load_previous_snapshot(slug: str) -> dict | None:
    out_dir = HISTORY / slug
    if not out_dir.exists():
        return None
    snapshots = sorted(out_dir.glob("*.json"))
    today_path = out_dir / f"{date.today().isoformat()}.json"
    prior = [s for s in snapshots if s != today_path]
    if not prior:
        return None
    try:
        with prior[-1].open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def prev_team_totals(prev: dict | None) -> dict[int, dict[str, int]]:
    """Returns {roster_id: {mode: total_value}} from the previous snapshot."""
    out: dict[int, dict[str, int]] = {}
    if not prev:
        return out
    for t in prev.get("teams", []):
        rid = t["roster_id"]
        modes = t.get("modes") or {}
        out[rid] = {m: modes.get(m, {}).get("total_value", 0) for m in MODES}
    return out


def position_strength(team_starters_by_pos: dict[str, int], league_pos_totals: dict[str, list[int]]) -> dict:
    """Per-position label for my team relative to the league.
    `league_pos_totals[pos]` is the sorted-desc list of all teams' values at
    that position; my rank is 1-indexed."""
    out = {}
    n = len(next(iter(league_pos_totals.values()), []))
    surplus_cutoff = max(1, n // 3)         # top third
    gap_cutoff = max(2, n - (n // 3) + 1)   # bottom third start
    for pos in SKILL_POSITIONS:
        my_value = team_starters_by_pos.get(pos, 0)
        totals = league_pos_totals.get(pos, [])
        rank = sum(1 for v in totals if v > my_value) + 1
        if rank <= surplus_cutoff:
            label = "surplus"
        elif rank >= gap_cutoff:
            label = "gap"
        else:
            label = "average"
        out[pos] = {"value": my_value, "league_rank": rank, "label": label}
    return out


def candidate_to_dict(c: TradeCandidate, pos_ranks: dict[str, int]) -> dict:
    def pdict(p: Player) -> dict:
        return {
            "sleeper_id": p.sleeper_id,
            "name": p.name,
            "position": p.position,
            "team": p.team,
            "age": p.age,
            "dynasty_value": p.dynasty_value,
            "redraft_value": p.redraft_value,
            "injury_status": p.injury_status,
            "pos_rank_in_league": pos_ranks.get(p.sleeper_id),
            "is_pick": p.position == "PICK",
        }
    return {
        "send": [pdict(p) for p in c.send],
        "receive": [pdict(p) for p in c.receive],
        "structure": c.structure,
        "tier": c.tier,
        "pick_flow": c.pick_flow,
        "my_lineup_change": c.my_lineup_change,
        "their_lineup_change": c.their_lineup_change,
        "my_asset_change": c.my_asset_change,
        "their_asset_change": c.their_asset_change,
        "my_value_delta": c.my_value_delta,
        "my_lineup_old": c.my_lineup_old,
        "my_lineup_new": c.my_lineup_new,
        "their_lineup_old": c.their_lineup_old,
        "their_lineup_new": c.their_lineup_new,
        "score": c.score,
    }


def build_trade_report(
    my_roster_id: int,
    rostered_by_team: dict[int, list[Player]],
    picks_by_team: dict[int, list[Player]],
    teams_data: list[dict],
    team_meta: dict[int, dict],
    slots: list[str],
    pos_ranks: dict[str, dict[str, int]],
) -> dict:
    """Returns the trades payload to attach to the league report."""
    vf = value_fn_for(TRADE_MODE)
    my_players = rostered_by_team[my_roster_id]
    my_picks = picks_by_team.get(my_roster_id, [])
    my_tradeable = my_players + my_picks

    league_pos_totals: dict[str, list[int]] = {pos: [] for pos in SKILL_POSITIONS}
    my_team_data = next(t for t in teams_data if t["roster_id"] == my_roster_id)
    for t in teams_data:
        for pos in SKILL_POSITIONS:
            league_pos_totals[pos].append(t["modes"][TRADE_MODE]["position_totals"].get(pos, 0))
    for pos in SKILL_POSITIONS:
        league_pos_totals[pos].sort(reverse=True)

    my_pos_strength = position_strength(
        my_team_data["modes"][TRADE_MODE]["position_totals"],
        league_pos_totals,
    )

    by_team: list[dict] = []
    all_candidates: list[tuple[int, TradeCandidate]] = []
    for rid, players_list in rostered_by_team.items():
        if rid == my_roster_id:
            continue
        their_picks = picks_by_team.get(rid, [])
        their_tradeable = players_list + their_picks

        candidates = find_trades(
            my_tradeable=my_tradeable,
            my_players=my_players,
            their_tradeable=their_tradeable,
            their_players=players_list,
            slots=slots,
            value_fn=vf,
        )
        top_for_team = candidates[:TOP_TRADES_PER_TEAM]
        by_team.append({
            "team": team_meta[rid],
            "their_rank_dynasty": next(
                t["modes"]["dynasty"]["rank"] for t in teams_data if t["roster_id"] == rid
            ),
            "their_rank_winnow": next(
                t["modes"]["winnow"]["rank"] for t in teams_data if t["roster_id"] == rid
            ),
            "candidate_count": len(candidates),
            "candidates": [candidate_to_dict(c, pos_ranks[TRADE_MODE]) for c in top_for_team],
        })
        for c in candidates:
            all_candidates.append((rid, c))

    # Group by tier across all partners.
    tiers = {"mutual": [], "buy": [], "sell": [], "package": [], "asymmetric": []}
    for rid, c in all_candidates:
        d = candidate_to_dict(c, pos_ranks[TRADE_MODE])
        d["partner_team_name"] = team_meta[rid]["team_name"]
        d["partner_owner"] = team_meta[rid]["owner_display_name"]
        d["partner_dynasty_rank"] = next(
            t["modes"]["dynasty"]["rank"] for t in teams_data if t["roster_id"] == rid
        )
        d["partner_winnow_rank"] = next(
            t["modes"]["winnow"]["rank"] for t in teams_data if t["roster_id"] == rid
        )
        tiers[c.tier].append(d)
    for tier in tiers:
        tiers[tier].sort(key=lambda d: d["score"], reverse=True)
        tiers[tier] = tiers[tier][:TOP_TRADES_PER_TIER]

    return {
        "my_team": {
            **team_meta[my_roster_id],
            "dynasty_rank": my_team_data["modes"]["dynasty"]["rank"],
            "winnow_rank": my_team_data["modes"]["winnow"]["rank"],
            "dynasty_total": my_team_data["modes"]["dynasty"]["total_value"],
            "winnow_total": my_team_data["modes"]["winnow"]["total_value"],
            "position_strength": my_pos_strength,
            "pick_count": len(my_picks),
            "pick_value": sum(p.dynasty_value for p in my_picks),
        },
        "by_team": by_team,
        "tiers": tiers,
        "tier_counts": {t: len(c) for t, c in tiers.items()},
        "total_candidates": len(all_candidates),
        "mode": TRADE_MODE,
    }


def build_league_report(league_id: str, slug: str, my_user_id: str | None = None) -> dict:
    league = data.get_league(league_id)
    users = {u["user_id"]: u for u in data.get_users(league_id)}
    rosters = data.get_rosters(league_id)
    sleeper_players = data.get_all_players()
    ppr = league["scoring_settings"].get("rec", 0.5)
    fc_values = data.get_dynasty_values(
        num_qbs=1,
        num_teams=league["total_rosters"],
        ppr=ppr,
    )
    index = data.build_player_index(sleeper_players, fc_values)
    slots = league["roster_positions"]
    previous = load_previous_snapshot(slug)
    prev_totals = prev_team_totals(previous)
    prev_date = previous.get("generated_at", "")[:10] if previous else None

    # Pick ownership.
    traded_picks = data.get_traded_picks(league_id)
    pick_averages = data.pick_round_averages(fc_values)
    draft_rounds = league["settings"].get("draft_rounds", 3)
    current_season = int(league["season"])
    pick_seasons = [str(current_season + i) for i in range(PICK_SEASONS_AHEAD)]
    roster_ids = [r["roster_id"] for r in rosters]
    pick_ownership = data.compute_pick_ownership(
        roster_ids=roster_ids,
        draft_rounds=draft_rounds,
        seasons=pick_seasons,
        traded_picks=traded_picks,
        pick_averages=pick_averages,
    )

    # First pass: collect active players per team.
    rostered_by_team: dict[int, list[Player]] = {}
    picks_by_team: dict[int, list[Player]] = {}
    team_meta: dict[int, dict] = {}
    for roster in rosters:
        owner = users.get(roster["owner_id"], {})
        taxi = set(roster.get("taxi") or [])
        reserve = set(roster.get("reserve") or [])
        active_ids = [
            pid for pid in (roster.get("players") or [])
            if pid not in taxi and pid not in reserve
        ]
        players_list = [data.get_player(index, sleeper_players, pid) for pid in active_ids]
        rostered_by_team[roster["roster_id"]] = players_list
        team_meta[roster["roster_id"]] = {
            "roster_id": roster["roster_id"],
            "team_name": team_name(owner),
            "owner_display_name": owner.get("display_name", ""),
            "owner_avatar": owner_avatar(owner),
        }

    # Convert DraftPicks → Player objects for the trade pool.
    for rid, picks in pick_ownership.items():
        picks_by_team[rid] = [
            data.pick_to_player(p, original_team_name=team_meta.get(p.original_roster_id, {}).get("team_name"))
            for p in picks
        ]

    # Per-mode positional rank tables (same player can rank differently per mode).
    pos_ranks: dict[str, dict[str, int]] = {
        mode: compute_league_pos_ranks(rostered_by_team, mode) for mode in MODES
    }

    # Build per-team, per-mode lineup + bench.
    teams: list[dict] = []
    for rid, players_list in rostered_by_team.items():
        meta = team_meta[rid]
        team = dict(meta)
        team["modes"] = {}

        for mode in MODES:
            vf = value_fn_for(mode)
            lineup = optimal_lineup(players_list, slots, value_fn=vf)
            starter_ids = {p.sleeper_id for _, p in lineup.assignments}

            position_totals = {pos: 0 for pos in POS_ORDER}
            for _, p in lineup.assignments:
                if p.position in position_totals:
                    position_totals[p.position] += vf(p)

            bench = [p for p in players_list if p.sleeper_id not in starter_ids and p.is_skill]
            bench.sort(key=vf, reverse=True)
            top_bench = bench[:BENCH_DEPTH]

            prev_total = prev_totals.get(rid, {}).get(mode)
            delta_vs_prev = None
            if prev_total is not None:
                delta_vs_prev = lineup.total_value - prev_total

            team["modes"][mode] = {
                "total_value": lineup.total_value,
                "position_totals": position_totals,
                "lineup": [
                    player_to_dict(p, slot, vf(p), pos_ranks[mode].get(p.sleeper_id))
                    for slot, p in lineup.assignments
                ],
                "bench": [
                    player_to_dict(p, None, vf(p), pos_ranks[mode].get(p.sleeper_id))
                    for p in top_bench
                ],
                "delta_vs_prev": delta_vs_prev,
            }
        teams.append(team)

    # Assign per-mode ranks based on each mode's total_value.
    for mode in MODES:
        teams.sort(key=lambda t: t["modes"][mode]["total_value"], reverse=True)
        for rank, t in enumerate(teams, 1):
            t["modes"][mode]["rank"] = rank

    # rank_delta = dynasty_rank - winnow_rank.
    # Positive  = better positioned long-term than short-term  (rebuild)
    # Negative  = better positioned short-term than long-term  (win-now veteran)
    for t in teams:
        t["rank_delta"] = t["modes"]["dynasty"]["rank"] - t["modes"]["winnow"]["rank"]

    # Default sort: by dynasty rank for the JSON stable order.
    teams.sort(key=lambda t: t["modes"]["dynasty"]["rank"])

    trade_report = None
    if my_user_id:
        my_roster_id = next(
            (rid for rid, m in team_meta.items()
             if next((r for r in rosters if r["roster_id"] == rid and r["owner_id"] == my_user_id), None)),
            None,
        )
        if my_roster_id is not None:
            trade_report = build_trade_report(
                my_roster_id=my_roster_id,
                rostered_by_team=rostered_by_team,
                picks_by_team=picks_by_team,
                teams_data=teams,
                team_meta=team_meta,
                slots=slots,
                pos_ranks=pos_ranks,
            )

    waiver_report = None
    if my_user_id:
        my_roster_id = next(
            (rid for rid, m in team_meta.items()
             if next((r for r in rosters if r["roster_id"] == rid and r["owner_id"] == my_user_id), None)),
            None,
        )
        if my_roster_id is not None:
            rostered_ids: set[str] = set()
            for r in rosters:
                rostered_ids.update(r.get("players") or [])
                rostered_ids.update(r.get("taxi") or [])
                rostered_ids.update(r.get("reserve") or [])
            available_players = [
                p for sid, p in index.items()
                if sid not in rostered_ids and p.position != "PICK"
            ]
            trending_adds = {
                str(t["player_id"]): t["count"]
                for t in data.get_trending(kind="add", lookback_hours=24, limit=50)
            }
            gap_positions: list[str] = []
            if trade_report:
                gap_positions = [
                    pos for pos, info in trade_report["my_team"]["position_strength"].items()
                    if info["label"] == "gap"
                ]
            waiver_report = build_waiver_report(
                my_roster=rostered_by_team[my_roster_id],
                available_players=available_players,
                trending_adds=trending_adds,
                gap_positions=gap_positions,
            )

    return {
        "slug": slug,
        "name": league["name"],
        "season": league["season"],
        "league_id": league_id,
        "total_rosters": league["total_rosters"],
        "ppr": ppr,
        "pass_td": league["scoring_settings"].get("pass_td", 4),
        "roster_positions": slots,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "previous_snapshot_date": prev_date,
        "teams": teams,
        "trades": trade_report,
        "waivers": waiver_report,
    }


def write_history(slug: str, report: dict) -> None:
    """Stamp a daily snapshot. Overwrites if run multiple times same day."""
    out_dir = HISTORY / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{date.today().isoformat()}.json"
    with out.open("w") as f:
        json.dump(report, f, indent=2)


def render_site(reports: list[dict]) -> None:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = lambda v: f"{v:,}" if v is not None else "—"
    env.filters["signed"] = lambda v: ("+" if v > 0 else "") + f"{v:,}" if v is not None else ""

    def teams_sorted_by(teams, mode):
        return sorted(teams, key=lambda t: t["modes"][mode]["rank"])
    env.globals["teams_sorted_by"] = teams_sorted_by

    SITE.mkdir(exist_ok=True)
    (SITE / "leagues").mkdir(exist_ok=True)

    league_tmpl = env.get_template("league.html.j2")
    trades_tmpl = env.get_template("trades.html.j2")
    waivers_tmpl = env.get_template("waivers.html.j2")
    for r in reports:
        out_dir = SITE / "leagues" / r["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(league_tmpl.render(report=r))
        (out_dir / "data.json").write_text(json.dumps(r, indent=2))

        if r.get("trades"):
            trades_dir = out_dir / "trades"
            trades_dir.mkdir(exist_ok=True)
            (trades_dir / "index.html").write_text(trades_tmpl.render(report=r))

        if r.get("waivers"):
            waivers_dir = out_dir / "waivers"
            waivers_dir.mkdir(exist_ok=True)
            (waivers_dir / "index.html").write_text(waivers_tmpl.render(report=r))

    landing_tmpl = env.get_template("landing.html.j2")
    (SITE / "index.html").write_text(landing_tmpl.render(
        reports=reports,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    ))

    css_src = TEMPLATES / "style.css"
    if css_src.exists():
        (SITE / "style.css").write_text(css_src.read_text())

    js_src = TEMPLATES / "app.js"
    if js_src.exists():
        (SITE / "app.js").write_text(js_src.read_text())


def main() -> None:
    with LEAGUES_CFG.open() as f:
        cfg = yaml.safe_load(f)

    reports = []
    for entry in cfg["leagues"]:
        print(f"Building {entry['slug']}...")
        r = build_league_report(
            entry["league_id"],
            entry["slug"],
            my_user_id=entry.get("my_user_id"),
        )
        write_history(entry["slug"], r)
        reports.append(r)

    render_site(reports)
    print(f"\nWrote {len(reports)} league report(s) to {SITE}")


if __name__ == "__main__":
    main()
