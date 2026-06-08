"""Season-long projection overlay (P2: ESPN / FantasyPros swap-in).

Today FantasyCalc's market-driven ``redraftValue`` is the only win-now signal
we use. Once ESPN or FantasyPros publish their 2026 projections (historically
late July), we'll overlay those onto ``Player.redraft_value`` so lineups, the
trade finder, targets, and rankings all run on real stat-based projections.

**Stub status (June 2026):** ``fetch_projections`` returns ``{}`` so the
pipeline call is a no-op and FC values stay in place. The scaffolding lives
here so the July work is a single function body, not a refactor.

When wiring a real source, mind:

- **Scale.** FantasyCalc values are market-calibrated trade values (~100s to
  ~10,000s). Raw fantasy-point projections (e.g. 280 pts/season) are a
  different scale — overlay them naively and lineup totals, asset-change math,
  and trade tiers will read wrong. Either normalize to the FC scale on the way
  in, or commit to a full unit change downstream.
- **Player ID join.** Overlay is keyed on Sleeper IDs. If the source uses
  ESPN IDs, join via ``Player.espn_id`` (already on the model).
- **Coverage.** A partial overlay (only a subset of players matched) leaves
  the rest on FC redraft — make sure that's the desired behavior, or fall
  back uniformly when match-rate is too low.

Candidate sources to evaluate in July:

- **ESPN.** ``fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players``
  exposes projections in the ``stats[]`` array under the projection stat
  source. Undocumented but widely used.
- **FantasyPros.** ``www.fantasypros.com/nfl/projections/{pos}.php`` ships a
  free preseason ECR consensus table; HTML scrape.
- **nflverse.** Strong for historical play-by-play and usage; weaker for
  forward projections specifically.
"""
from __future__ import annotations


def fetch_projections(season: str) -> dict[str, int]:
    """Return ``{sleeper_id: projected_redraft_value_on_FC_scale}`` for the
    given season. Empty until a 2026 source is wired up (target: late July).

    The contract is FC-scale integers so the overlay is a straight assignment
    into ``Player.redraft_value``; any unit conversion happens here.
    """
    # TODO(late-July 2026): wire ESPN site API or FantasyPros HTML.
    # Tracked: github.com/stephenmsoward-cmd/Stephen-dynasty-football-assistant/issues/1
    return {}


def apply_projections(player_index: dict, projections: dict[str, int]) -> int:
    """Overlay projected values onto ``Player.redraft_value``. Returns the
    number of players updated. No-op when ``projections`` is empty — today's
    stub behavior."""
    if not projections:
        return 0
    updated = 0
    for sleeper_id, value in projections.items():
        player = player_index.get(sleeper_id)
        if player is not None:
            player.redraft_value = value
            updated += 1
    return updated
