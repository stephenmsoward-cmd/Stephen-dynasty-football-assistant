"""Sleeper + FantasyCalc clients with simple file-based TTL cache."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

SLEEPER_BASE = "https://api.sleeper.app/v1"
FANTASYCALC_BASE = "https://api.fantasycalc.com"


def _cached_get(url: str, cache_key: str, ttl_seconds: int) -> Any:
    path = CACHE_DIR / f"{cache_key}.json"
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl_seconds:
        with path.open() as f:
            return json.load(f)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    with path.open("w") as f:
        json.dump(data, f)
    return data


# --- Sleeper ---

def get_league(league_id: str) -> dict:
    return _cached_get(
        f"{SLEEPER_BASE}/league/{league_id}",
        f"sleeper_league_{league_id}",
        ttl_seconds=3600,
    )


def get_users(league_id: str) -> list[dict]:
    return _cached_get(
        f"{SLEEPER_BASE}/league/{league_id}/users",
        f"sleeper_users_{league_id}",
        ttl_seconds=3600,
    )


def get_rosters(league_id: str) -> list[dict]:
    return _cached_get(
        f"{SLEEPER_BASE}/league/{league_id}/rosters",
        f"sleeper_rosters_{league_id}",
        ttl_seconds=3600,
    )


def get_traded_picks(league_id: str) -> list[dict]:
    """Returns trades involving draft picks. Each entry:
    {round, season, roster_id (original), owner_id (current), previous_owner_id}."""
    return _cached_get(
        f"{SLEEPER_BASE}/league/{league_id}/traded_picks",
        f"sleeper_traded_picks_{league_id}",
        ttl_seconds=3600,
    )


def get_trending(kind: str = "add", lookback_hours: int = 24, limit: int = 50) -> list[dict]:
    """Sleeper's community-trending list. kind = 'add' or 'drop'.
    Returns [{player_id, count}], sorted desc by count."""
    return _cached_get(
        f"{SLEEPER_BASE}/players/nfl/trending/{kind}?lookback_hours={lookback_hours}&limit={limit}",
        f"sleeper_trending_{kind}_{lookback_hours}h_{limit}",
        ttl_seconds=3600,  # trending data is genuinely time-sensitive
    )


def get_all_players() -> dict[str, dict]:
    # Sleeper recommends fetching this no more than once per day.
    return _cached_get(
        f"{SLEEPER_BASE}/players/nfl",
        "sleeper_players_nfl",
        ttl_seconds=86400,
    )


# --- FantasyCalc ---

def get_dynasty_values(num_qbs: int = 1, num_teams: int = 10, ppr: float = 0.5) -> list[dict]:
    url = (
        f"{FANTASYCALC_BASE}/values/current"
        f"?isDynasty=true&numQbs={num_qbs}&numTeams={num_teams}&ppr={ppr}"
    )
    return _cached_get(
        url,
        f"fantasycalc_dyn_qb{num_qbs}_t{num_teams}_ppr{ppr}",
        ttl_seconds=86400,
    )


# --- Joined player model ---

@dataclass
class Player:
    sleeper_id: str
    name: str
    position: str
    team: str | None
    age: float | None
    years_exp: int | None
    dynasty_value: int       # multi-year, age-weighted (FantasyCalc `value`)
    redraft_value: int       # this season only (FantasyCalc `redraftValue`)
    position_rank: int | None
    injury_status: str | None

    @property
    def is_skill(self) -> bool:
        return self.position in {"QB", "RB", "WR", "TE"}

    def value_for(self, mode: str) -> int:
        return self.redraft_value if mode == "winnow" else self.dynasty_value


def build_player_index(
    sleeper_players: dict[str, dict],
    fc_values: list[dict],
) -> dict[str, Player]:
    """Return {sleeper_id: Player} for every player FantasyCalc has values for,
    plus any rostered player not in FC (with value=0)."""
    fc_by_sleeper: dict[str, dict] = {}
    for entry in fc_values:
        sid = entry["player"].get("sleeperId")
        if sid:
            fc_by_sleeper[sid] = entry

    index: dict[str, Player] = {}
    for sid, entry in fc_by_sleeper.items():
        p = entry["player"]
        sleeper_p = sleeper_players.get(sid, {})
        name = sleeper_p.get("full_name") or p.get("name") or sid
        index[sid] = Player(
            sleeper_id=sid,
            name=name,
            position=p.get("position") or sleeper_p.get("position") or "?",
            team=sleeper_p.get("team") or p.get("maybeTeam"),
            age=sleeper_p.get("age") or p.get("maybeAge"),
            years_exp=sleeper_p.get("years_exp") or p.get("maybeYoe"),
            dynasty_value=entry.get("value", 0),
            redraft_value=entry.get("redraftValue", 0),
            position_rank=entry.get("positionRank"),
            injury_status=sleeper_p.get("injury_status"),
        )
    return index


def get_player(
    index: dict[str, Player],
    sleeper_players: dict[str, dict],
    sleeper_id: str,
) -> Player:
    """Look up a player, falling back to Sleeper data with value=0 if FC has no entry.
    Handles team defenses (e.g. 'KC') and the empty starter slot ('0')."""
    if sleeper_id in index:
        return index[sleeper_id]
    sp = sleeper_players.get(sleeper_id, {})
    # Team defenses come through as team abbreviations (e.g. "KC", "BAL")
    if len(sleeper_id) <= 3 and sleeper_id.isalpha():
        return Player(
            sleeper_id=sleeper_id,
            name=f"{sleeper_id} DEF",
            position="DEF",
            team=sleeper_id,
            age=None,
            years_exp=None,
            dynasty_value=0,
            redraft_value=0,
            position_rank=None,
            injury_status=None,
        )
    return Player(
        sleeper_id=sleeper_id,
        name=sp.get("full_name") or sleeper_id,
        position=sp.get("position") or "?",
        team=sp.get("team"),
        age=sp.get("age"),
        years_exp=sp.get("years_exp"),
        dynasty_value=0,
        redraft_value=0,
        position_rank=None,
        injury_status=sp.get("injury_status"),
    )


# --- Draft picks ---
# FantasyCalc tracks picks for the next upcoming draft only (2026 as of writing).
# For seasons it doesn't track (2027+), we apply a discount to the same round's
# value: futures are worth less because of time and uncertainty.
FUTURE_PICK_DISCOUNT = 0.85
_PICK_NAME_RE = re.compile(r"(\d{4}) Pick (\d+)\.(\d+)")


def pick_round_averages(fc_values: list[dict]) -> dict[tuple[str, int], int]:
    """Returns {(season, round): avg_dynasty_value} across all FC pick slots."""
    by_round: dict[tuple[str, int], list[int]] = {}
    for entry in fc_values:
        p = entry["player"]
        if p.get("position") != "PICK":
            continue
        m = _PICK_NAME_RE.match(p.get("name", ""))
        if not m:
            continue
        season, rnd, _slot = m.groups()
        by_round.setdefault((season, int(rnd)), []).append(entry.get("value", 0))
    return {k: sum(v) // len(v) for k, v in by_round.items()}


def pick_value(
    season: str,
    rnd: int,
    pick_averages: dict[tuple[str, int], int],
    latest_known_season: str | None = None,
) -> int:
    """Look up a pick's expected dynasty value. Falls back to the discounted
    most-recent-known season if FC doesn't track this future season."""
    if (season, rnd) in pick_averages:
        return pick_averages[(season, rnd)]
    if latest_known_season and (latest_known_season, rnd) in pick_averages:
        try:
            years_out = int(season) - int(latest_known_season)
        except ValueError:
            years_out = 1
        years_out = max(1, years_out)
        return int(pick_averages[(latest_known_season, rnd)] * (FUTURE_PICK_DISCOUNT ** years_out))
    return 0


def latest_pick_season(pick_averages: dict[tuple[str, int], int]) -> str | None:
    seasons = {s for s, _ in pick_averages.keys()}
    return max(seasons) if seasons else None


@dataclass
class DraftPick:
    season: str
    round: int
    original_roster_id: int   # who would have this by default
    current_roster_id: int    # who has it now after trades
    dynasty_value: int

    def sleeper_id(self) -> str:
        return f"PICK_{self.season}_R{self.round}_O{self.original_roster_id}"

    def display_name(self, original_team_name: str | None = None) -> str:
        if original_team_name:
            return f"{self.season} R{self.round} ({original_team_name})"
        return f"{self.season} R{self.round}"


def compute_pick_ownership(
    roster_ids: list[int],
    draft_rounds: int,
    seasons: list[str],
    traded_picks: list[dict],
    pick_averages: dict[tuple[str, int], int],
) -> dict[int, list[DraftPick]]:
    """Walks every (season, round, original_owner) pick, applies trades, and
    returns {current_owner_roster_id: [DraftPick, ...]}."""
    # Index trades by (season, round, original_owner) → current_owner
    trade_index: dict[tuple[str, int, int], int] = {
        (t["season"], t["round"], t["roster_id"]): t["owner_id"]
        for t in traded_picks
    }
    latest = latest_pick_season(pick_averages)
    by_owner: dict[int, list[DraftPick]] = {rid: [] for rid in roster_ids}
    for season in seasons:
        for rnd in range(1, draft_rounds + 1):
            value = pick_value(season, rnd, pick_averages, latest_known_season=latest)
            if value <= 0:
                continue
            for original in roster_ids:
                current = trade_index.get((season, rnd, original), original)
                if current not in by_owner:
                    by_owner[current] = []
                by_owner[current].append(DraftPick(
                    season=season,
                    round=rnd,
                    original_roster_id=original,
                    current_roster_id=current,
                    dynasty_value=value,
                ))
    return by_owner


def pick_to_player(pick: DraftPick, original_team_name: str | None = None) -> Player:
    """Express a draft pick as a Player so it flows through the trade pool.
    position='PICK' keeps it out of optimal lineups and bench depth (is_skill
    only matches QB/RB/WR/TE)."""
    return Player(
        sleeper_id=pick.sleeper_id(),
        name=pick.display_name(original_team_name),
        position="PICK",
        team=None,
        age=None,
        years_exp=None,
        dynasty_value=pick.dynasty_value,
        redraft_value=0,
        position_rank=None,
        injury_status=None,
    )
