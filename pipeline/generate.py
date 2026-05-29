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
from trades import TradeCandidate, find_trades, find_acquisition_packages
from pitch import build_partner_pitch
from waivers import build_waiver_report
from draft import build_draft_report
from news import build_news_feed
from rankings import build_power_rankings
from compare import build_compare_report
from diagnosis import build_team_diagnosis
from history import build_team_series, sparkline_svg
from og import make_og_image

ROOT = Path(__file__).parent.parent
SITE = ROOT / "docs"
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
BASE_URL = "https://stephenmsoward-cmd.github.io/Stephen-dynasty-football-assistant"


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


def _run_trade_search(
    mode: str,
    my_players: list[Player],
    my_tradeable: list[Player],
    rostered_by_team: dict[int, list[Player]],
    picks_by_team: dict[int, list[Player]],
    my_roster_id: int,
    slots: list[str],
    teams_data: list[dict],
    team_meta: dict[int, dict],
    pos_ranks_for_mode: dict[str, int],
    strength_by_team: dict[int, dict],
    num_teams: int,
) -> dict:
    """Compute all candidates + tiers for one value mode (dynasty or winnow).

    `mode` is MY lens (the toggle). Each partner's lineup is judged under
    THEIR own timeline, inferred from their trajectory: win-now partners by
    redraft value, rebuild/balanced partners by dynasty value."""
    my_vf = value_fn_for(mode)
    rank_by_team = {
        t["roster_id"]: (t["modes"]["dynasty"]["rank"], t["modes"]["winnow"]["rank"])
        for t in teams_data
    }

    def trajectory_of(rid: int) -> str:
        dyn, wn = rank_by_team[rid]
        delta = dyn - wn
        if delta > 2:
            return "win-now"
        if delta < -2:
            return "rebuild"
        return "balanced"

    def their_value_fn(rid: int):
        # Win-now teams optimize for this-season production; everyone else for
        # long-term dynasty value.
        return value_fn_for("winnow") if trajectory_of(rid) == "win-now" else value_fn_for("dynasty")

    def pitch_for(c: TradeCandidate, rid: int) -> str:
        dyn_rank, wn_rank = rank_by_team[rid]
        return build_partner_pitch(
            send=c.send,
            receive=c.receive,
            partner_name=team_meta[rid]["team_name"],
            partner_strength=strength_by_team.get(rid, {}),
            dynasty_rank=dyn_rank,
            winnow_rank=wn_rank,
            num_teams=num_teams,
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
            my_value_fn=my_vf,
            their_value_fn=their_value_fn(rid),
            # My lens: win-now mode means I only count lineup gains; dynasty
            # mode lets asset value count too. Partner: judged by their own
            # trajectory (win-now teams won't accept a worse win-now lineup).
            my_timeline=("win-now" if mode == "winnow" else "balanced"),
            their_timeline=trajectory_of(rid),
        )
        top_for_team = candidates[:TOP_TRADES_PER_TEAM]
        team_candidate_dicts = []
        for c in top_for_team:
            d = candidate_to_dict(c, pos_ranks_for_mode)
            d["partner_pitch"] = pitch_for(c, rid)
            d["partner_trajectory"] = trajectory_of(rid)
            team_candidate_dicts.append(d)
        by_team.append({
            "team": team_meta[rid],
            "their_rank_dynasty": rank_by_team[rid][0],
            "their_rank_winnow": rank_by_team[rid][1],
            "candidate_count": len(candidates),
            "candidates": team_candidate_dicts,
        })
        for c in candidates:
            all_candidates.append((rid, c))

    tiers = {"mutual": [], "buy": [], "sell": [], "package": [], "asymmetric": []}
    for rid, c in all_candidates:
        d = candidate_to_dict(c, pos_ranks_for_mode)
        d["partner_team_name"] = team_meta[rid]["team_name"]
        d["partner_owner"] = team_meta[rid]["owner_display_name"]
        d["partner_dynasty_rank"] = rank_by_team[rid][0]
        d["partner_winnow_rank"] = rank_by_team[rid][1]
        d["partner_pitch"] = pitch_for(c, rid)
        d["partner_trajectory"] = trajectory_of(rid)
        tiers[c.tier].append(d)
    for tier in tiers:
        tiers[tier].sort(key=lambda d: d["score"], reverse=True)
        tiers[tier] = tiers[tier][:TOP_TRADES_PER_TIER]

    return {
        "by_team": by_team,
        "tiers": tiers,
        "tier_counts": {t: len(c) for t, c in tiers.items()},
        "total_candidates": len(all_candidates),
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
    """Returns the trades payload, with candidates computed under BOTH modes."""
    my_players = rostered_by_team[my_roster_id]
    my_picks = picks_by_team.get(my_roster_id, [])
    my_tradeable = my_players + my_picks

    my_team_data = next(t for t in teams_data if t["roster_id"] == my_roster_id)

    # Per-mode positional strength for MY team (gaps shift between modes).
    position_strengths: dict[str, dict] = {}
    league_pos_totals_by_mode: dict[str, dict[str, list[int]]] = {}
    for mode in MODES:
        league_pos_totals: dict[str, list[int]] = {pos: [] for pos in SKILL_POSITIONS}
        for t in teams_data:
            for pos in SKILL_POSITIONS:
                league_pos_totals[pos].append(t["modes"][mode]["position_totals"].get(pos, 0))
        for pos in SKILL_POSITIONS:
            league_pos_totals[pos].sort(reverse=True)
        league_pos_totals_by_mode[mode] = league_pos_totals
        position_strengths[mode] = position_strength(
            my_team_data["modes"][mode]["position_totals"],
            league_pos_totals,
        )

    # Dynasty position strength for EVERY team — drives the partner pitch.
    # Dynasty (not the active trade mode) because the pitch is about the
    # partner's roster shape and timeline, which is a dynasty-level signal.
    strength_by_team: dict[int, dict] = {
        t["roster_id"]: position_strength(
            t["modes"]["dynasty"]["position_totals"],
            league_pos_totals_by_mode["dynasty"],
        )
        for t in teams_data
    }

    # Run the trade search once per mode.
    mode_results: dict[str, dict] = {}
    for mode in MODES:
        mode_results[mode] = _run_trade_search(
            mode=mode,
            my_players=my_players,
            my_tradeable=my_tradeable,
            rostered_by_team=rostered_by_team,
            picks_by_team=picks_by_team,
            my_roster_id=my_roster_id,
            slots=slots,
            teams_data=teams_data,
            team_meta=team_meta,
            pos_ranks_for_mode=pos_ranks[mode],
            strength_by_team=strength_by_team,
            num_teams=len(teams_data),
        )

    targets = build_targets(
        my_roster_id=my_roster_id,
        rostered_by_team=rostered_by_team,
        picks_by_team=picks_by_team,
        teams_data=teams_data,
        team_meta=team_meta,
        slots=slots,
        strength_by_team=strength_by_team,
        num_teams=len(teams_data),
    )

    return {
        "my_team": {
            **team_meta[my_roster_id],
            "dynasty_rank": my_team_data["modes"]["dynasty"]["rank"],
            "winnow_rank": my_team_data["modes"]["winnow"]["rank"],
            "dynasty_total": my_team_data["modes"]["dynasty"]["total_value"],
            "winnow_total": my_team_data["modes"]["winnow"]["total_value"],
            "position_strength": position_strengths,
            "pick_count": len(my_picks),
            "pick_value": sum(p.dynasty_value for p in my_picks),
        },
        "modes": mode_results,
        "targets": targets,
        "mode": TRADE_MODE,
    }


TARGETS_MIN_VALUE = 1500       # ignore depth pieces as targets
TARGETS_MIN_IMPROVEMENT = 100  # must meaningfully lift my optimal lineup
TOP_TARGETS = 12


def _simple_player_dict(p: Player) -> dict:
    return {
        "sleeper_id": p.sleeper_id,
        "name": p.name,
        "position": p.position,
        "team": p.team,
        "age": p.age,
        "dynasty_value": p.dynasty_value,
        "redraft_value": p.redraft_value,
        "injury_status": p.injury_status,
        "is_pick": p.position == "PICK",
    }


def _team_trajectory(dynasty_rank: int, winnow_rank: int) -> str:
    delta = dynasty_rank - winnow_rank
    if delta > 2:
        return "win-now"
    if delta < -2:
        return "rebuild"
    return "balanced"


# How many of the top players (by dynasty value) at each position, on OTHER
# rosters, are eligible to target via the picker.
POSITION_PICK_LIMITS = {"QB": 10, "RB": 20, "WR": 20, "TE": 10}
TOP_FEATURED = 12


def build_targets(
    my_roster_id: int,
    rostered_by_team: dict[int, list[Player]],
    picks_by_team: dict[int, list[Player]],
    teams_data: list[dict],
    team_meta: dict[int, dict],
    slots: list[str],
    strength_by_team: dict[int, dict],
    num_teams: int,
) -> dict:
    """Acquisition packages for the top players at each position on other
    rosters (top 20 RB/WR, top 10 QB/TE). Returns:
      - index: {sleeper_id: entry} for the picker
      - picker: position-grouped option lists for the dropdown
      - featured: the entries that most improve MY lineup (suggested targets)

    Dynasty-mode targeting. Packages are judged for partner-acceptance under
    the partner's own timeline."""
    dyn_vf = value_fn_for("dynasty")
    my_players = rostered_by_team[my_roster_id]
    my_tradeable = my_players + picks_by_team.get(my_roster_id, [])
    my_base_lineup = optimal_lineup(my_players, slots, value_fn=dyn_vf).total_value

    rank_by_team = {
        t["roster_id"]: (t["modes"]["dynasty"]["rank"], t["modes"]["winnow"]["rank"])
        for t in teams_data
    }

    # Owning team per player (only other rosters).
    owner_of: dict[str, int] = {}
    by_position: dict[str, list[Player]] = {pos: [] for pos in POSITION_PICK_LIMITS}
    for rid, players in rostered_by_team.items():
        if rid == my_roster_id:
            continue
        for p in players:
            if p.position in by_position and p.dynasty_value > 0:
                by_position[p.position].append(p)
                owner_of[p.sleeper_id] = rid

    # Pickable set: top-N by dynasty value per position.
    pickable: list[Player] = []
    for pos, limit in POSITION_PICK_LIMITS.items():
        ranked = sorted(by_position[pos], key=lambda p: p.dynasty_value, reverse=True)
        pickable.extend(ranked[:limit])

    def entry_for(p: Player) -> dict:
        rid = owner_of[p.sleeper_id]
        their_players = rostered_by_team[rid]
        their_tradeable = their_players + picks_by_team.get(rid, [])
        dyn_rank, wn_rank = rank_by_team[rid]
        inferred = _team_trajectory(dyn_rank, wn_rank)

        improvement = optimal_lineup(my_players + [p], slots, value_fn=dyn_vf).total_value - my_base_lineup

        # Compute packages under each possible timeline the user might assign
        # to this manager — so the override toggle has real data to show.
        packages_by_timeline: dict[str, list[dict]] = {}
        for tl in ("win-now", "balanced", "rebuild"):
            their_vf = value_fn_for("winnow") if tl == "win-now" else value_fn_for("dynasty")
            pkgs = find_acquisition_packages(
                target=p,
                my_tradeable=my_tradeable,
                my_players=my_players,
                their_tradeable=their_tradeable,
                their_players=their_players,
                slots=slots,
                my_value_fn=dyn_vf,
                their_value_fn=their_vf,
                their_timeline=tl,
            )
            packages_by_timeline[tl] = [{
                "send": [_simple_player_dict(sp) for sp in c.send],
                "my_lineup_change": c.my_lineup_change,
                "their_lineup_change": c.their_lineup_change,
                "my_value_delta": c.my_value_delta,
                "pitch": build_partner_pitch(
                    send=c.send,
                    receive=c.receive,
                    partner_name=team_meta[rid]["team_name"],
                    partner_strength=strength_by_team.get(rid, {}),
                    dynasty_rank=dyn_rank,
                    winnow_rank=wn_rank,
                    num_teams=num_teams,
                    trajectory_override=tl,
                ),
            } for c in pkgs]

        return {
            "player": _simple_player_dict(p),
            "owner_team": team_meta[rid]["team_name"],
            "owner_owner": team_meta[rid]["owner_display_name"],
            "inferred_trajectory": inferred,
            "owner_dynasty_rank": dyn_rank,
            "owner_winnow_rank": wn_rank,
            "my_lineup_improvement": improvement,
            "packages_by_timeline": packages_by_timeline,
        }

    index: dict[str, dict] = {p.sleeper_id: entry_for(p) for p in pickable}

    # Picker dropdown: grouped by position, ordered by dynasty value.
    picker = []
    for pos in ["QB", "RB", "WR", "TE"]:
        ranked = sorted(by_position[pos], key=lambda p: p.dynasty_value, reverse=True)[:POSITION_PICK_LIMITS[pos]]
        picker.append({
            "position": pos,
            "players": [
                {
                    "id": p.sleeper_id,
                    "label": f"{p.name} ({p.team or 'FA'}) — {index[p.sleeper_id]['owner_team']}",
                }
                for p in ranked
            ],
        })

    # Featured: best lineup-improvers, for the default suggestions view.
    featured = sorted(
        [e for e in index.values() if e["my_lineup_improvement"] >= TARGETS_MIN_IMPROVEMENT],
        key=lambda e: e["my_lineup_improvement"],
        reverse=True,
    )[:TOP_FEATURED]

    return {"index": index, "picker": picker, "featured": featured}


def build_league_report(
    league_id: str,
    slug: str,
    my_user_id: str | None = None,
    my_draft_slots: list[str] | None = None,
) -> dict:
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

    # Roster diagnosis: an opinionated read per team (direction + next move).
    # Uses dynasty positional strength against the league, so compute the
    # league-wide position totals once and label each team off them.
    diag_pos_totals: dict[str, list[int]] = {pos: [] for pos in SKILL_POSITIONS}
    for t in teams:
        for pos in SKILL_POSITIONS:
            diag_pos_totals[pos].append(t["modes"]["dynasty"]["position_totals"].get(pos, 0))
    for pos in SKILL_POSITIONS:
        diag_pos_totals[pos].sort(reverse=True)
    for t in teams:
        rid = t["roster_id"]
        my_picks = picks_by_team.get(rid, [])
        t["diagnosis"] = build_team_diagnosis(
            team_name=t["team_name"],
            dynasty_rank=t["modes"]["dynasty"]["rank"],
            winnow_rank=t["modes"]["winnow"]["rank"],
            num_teams=len(teams),
            position_strength=position_strength(
                t["modes"]["dynasty"]["position_totals"], diag_pos_totals
            ),
            starters=t["modes"]["dynasty"]["lineup"],
            pick_count=len(my_picks),
            pick_value=sum(p.dynasty_value for p in my_picks),
        )

    # Resolve "my" roster once, so the overview can surface my diagnosis.
    my_roster_id = None
    if my_user_id:
        my_roster_id = next(
            (r["roster_id"] for r in rosters if r["owner_id"] == my_user_id), None
        )

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
                # Use dynasty-mode gaps for the waiver page (consistent with the
                # roster's long-term shape; win-now gaps shift with redraft values).
                strength = trade_report["my_team"]["position_strength"]["dynasty"]
                gap_positions = [pos for pos, info in strength.items() if info["label"] == "gap"]
            # Starters in my dynasty optimal lineup — never suggest dropping these.
            my_team_record = next(t for t in teams if t["roster_id"] == my_roster_id)
            my_starter_ids = {
                p["sleeper_id"] for p in my_team_record["modes"]["dynasty"]["lineup"]
            }
            waiver_report = build_waiver_report(
                my_roster=rostered_by_team[my_roster_id],
                available_players=available_players,
                trending_adds=trending_adds,
                gap_positions=gap_positions,
                starter_ids=my_starter_ids,
            )

    draft_report = None
    if my_draft_slots:
        # Available rookies = years_exp 0, not rostered, has FC value, not a pick.
        rostered_ids_all: set[str] = set()
        for r in rosters:
            rostered_ids_all.update(r.get("players") or [])
            rostered_ids_all.update(r.get("taxi") or [])
            rostered_ids_all.update(r.get("reserve") or [])
        available_rookies = [
            p for sid, p in index.items()
            if p.years_exp == 0
            and p.position != "PICK"
            and sid not in rostered_ids_all
        ]
        slot_values = data.pick_slot_values(fc_values)

        # Compute position_strength for every team so the draft model can
        # apply league-wide positional demand to its adjusted board.
        league_pos_totals: dict[str, list[int]] = {pos: [] for pos in SKILL_POSITIONS}
        for t in teams:
            for pos in SKILL_POSITIONS:
                league_pos_totals[pos].append(t["modes"]["dynasty"]["position_totals"].get(pos, 0))
        for pos in SKILL_POSITIONS:
            league_pos_totals[pos].sort(reverse=True)
        position_strengths_by_team = {
            t["roster_id"]: position_strength(
                t["modes"]["dynasty"]["position_totals"],
                league_pos_totals,
            )
            for t in teams
        }

        draft_report = build_draft_report(
            available_rookies=available_rookies,
            my_slots=my_draft_slots,
            season=league["season"],
            num_teams=league["total_rosters"],
            pick_slot_values=slot_values,
            position_strengths_by_team=position_strengths_by_team,
        )

    # Per-team time series from historical snapshots → sparkline SVGs.
    team_series = build_team_series(HISTORY / slug)
    sparklines_by_team: dict[int, dict[str, str]] = {}
    for t in teams:
        rid = t["roster_id"]
        series = team_series.get(rid, {"dynasty": [], "winnow": []})
        sparklines_by_team[rid] = {
            "dynasty": sparkline_svg([s["value"] for s in series["dynasty"]]),
            "winnow": sparkline_svg([s["value"] for s in series["winnow"]]),
            "dynasty_points": len(series["dynasty"]),
            "winnow_points": len(series["winnow"]),
        }
        t["sparkline"] = sparklines_by_team[rid]

    # Power rankings — composite of dynasty, win-now, and total asset value.
    rankings_payload = build_power_rankings(
        teams_data=teams,
        rostered_by_team=rostered_by_team,
        picks_by_team=picks_by_team,
    )

    # Compare-two-teams — only when we know which team is "yours".
    compare_payload = None
    if my_user_id:
        # Reuse my_roster_id resolution.
        my_rid = next(
            (r["roster_id"] for r in rosters if r["owner_id"] == my_user_id),
            None,
        )
        if my_rid is not None:
            compare_payload = build_compare_report(
                my_roster_id=my_rid,
                rostered_by_team=rostered_by_team,
                picks_by_team=picks_by_team,
                teams_data=teams,
                team_meta=team_meta,
            )

    # News feed — for the whole league, articles mentioning any rostered player.
    rostered_by_espn_id: dict[str, Player] = {}
    for players_list in rostered_by_team.values():
        for p in players_list:
            if p.espn_id:
                rostered_by_espn_id[p.espn_id] = p
    news_feed = build_news_feed(
        articles=data.get_nfl_news(limit=80),
        rostered_players_by_espn_id=rostered_by_espn_id,
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
        "my_roster_id": my_roster_id,
        "teams": teams,
        "trades": trade_report,
        "waivers": waiver_report,
        "draft": draft_report,
        "news": news_feed,
        "rankings": rankings_payload,
        "compare": compare_payload,
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
    env.globals["base_url"] = BASE_URL

    def teams_sorted_by(teams, mode):
        return sorted(teams, key=lambda t: t["modes"][mode]["rank"])
    env.globals["teams_sorted_by"] = teams_sorted_by

    SITE.mkdir(exist_ok=True)
    (SITE / "leagues").mkdir(exist_ok=True)

    league_tmpl = env.get_template("league.html.j2")
    trades_tmpl = env.get_template("trades.html.j2")
    waivers_tmpl = env.get_template("waivers.html.j2")
    draft_tmpl = env.get_template("draft.html.j2")
    rankings_tmpl = env.get_template("rankings.html.j2")
    compare_tmpl = env.get_template("compare.html.j2")
    targets_tmpl = env.get_template("targets.html.j2")
    for r in reports:
        out_dir = SITE / "leagues" / r["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(league_tmpl.render(report=r))
        (out_dir / "data.json").write_text(json.dumps(r, indent=2))

        if r.get("trades"):
            trades_dir = out_dir / "trades"
            trades_dir.mkdir(exist_ok=True)
            (trades_dir / "index.html").write_text(trades_tmpl.render(report=r))

        if r.get("trades") and r["trades"].get("targets"):
            targets_dir = out_dir / "targets"
            targets_dir.mkdir(exist_ok=True)
            (targets_dir / "index.html").write_text(targets_tmpl.render(report=r))

        if r.get("waivers"):
            waivers_dir = out_dir / "waivers"
            waivers_dir.mkdir(exist_ok=True)
            (waivers_dir / "index.html").write_text(waivers_tmpl.render(report=r))

        if r.get("draft"):
            draft_dir = out_dir / "draft"
            draft_dir.mkdir(exist_ok=True)
            (draft_dir / "index.html").write_text(draft_tmpl.render(report=r))

        if r.get("rankings"):
            rankings_dir = out_dir / "rankings"
            rankings_dir.mkdir(exist_ok=True)
            (rankings_dir / "index.html").write_text(rankings_tmpl.render(report=r))

        if r.get("compare"):
            compare_dir = out_dir / "compare"
            compare_dir.mkdir(exist_ok=True)
            (compare_dir / "index.html").write_text(compare_tmpl.render(report=r))

    landing_tmpl = env.get_template("landing.html.j2")
    (SITE / "index.html").write_text(landing_tmpl.render(
        reports=reports,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    ))

    css_src = TEMPLATES / "style.css"
    if css_src.exists():
        (SITE / "style.css").write_text(css_src.read_text())

    for js_name in ("app.js", "targets.js"):
        js_src = TEMPLATES / js_name
        if js_src.exists():
            (SITE / js_name).write_text(js_src.read_text())

    # OG card image (shared across all pages; per-page titles in meta tags).
    make_og_image(SITE / "og.png")


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
            my_draft_slots=entry.get("my_draft_slots"),
        )
        write_history(entry["slug"], r)
        reports.append(r)

    render_site(reports)
    print(f"\nWrote {len(reports)} league report(s) to {SITE}")


if __name__ == "__main__":
    main()
