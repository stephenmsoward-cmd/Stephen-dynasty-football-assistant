# Dynasty Tools

Static site that publishes nightly best-ball projections, trade analytics, and
waiver-wire recommendations for Sleeper dynasty fantasy football leagues.

A GitHub Action runs every night, pulls live data from
[Sleeper](https://docs.sleeper.com) and [FantasyCalc](https://fantasycalc.com),
runs the analysis pipeline, and publishes the results to GitHub Pages. Each
run also commits a dated JSON snapshot to `history/`, giving you a time series
of league state across the season for free.

## What's currently built

### Best-ball projections — Dynasty + Win-Now modes

For each team, compute the **optimal starting lineup** under the league's slot
configuration. A built-in toggle switches between:

- **Dynasty** — FantasyCalc dynasty trade values (multi-year, age-weighted).
  Best signal for long-term roster strength.
- **Win Now** — FantasyCalc *redraft* values (single-season, market-derived
  trade values). Aging veterans rank higher here than in dynasty mode.

> **A note on the Win-Now source.** FantasyCalc redraft values reflect
> consensus *trade value* for this season, not actual statistical
> projections (yards, TDs, points). They're a real signal but not a stat
> model. The `redraft_value` field in [`pipeline/data.py`](pipeline/data.py)
> is the swap-in point — when ESPN or FantasyPros publish their 2026
> statistical projections in late July, replacing FC redraft with those is
> a small change. The lineup math, modes, and trade finder all work the
> same way against whatever source feeds that field.

Because the two modes value players differently, **the optimal lineup can
shift between modes** — a younger backup may start in Dynasty, while an
aging veteran with more guaranteed snaps starts in Win-Now. This surfaces
real strategic timing decisions.

Additional signals on every report:

- **Rank-delta column** — each team's rank in the *other* mode, with an
  arrow showing the shift. Teams with a big delta between Dynasty and
  Win-Now ranks reveal a clear timeline strategy (rebuild vs. veteran-heavy).
- **Position rank in league** — every player gets a tag (e.g.
  `WR#3`) showing where they rank against every other rostered player at
  their position, under the active mode.
- **Top bench preview** — three highest-value non-starters per team.
- **Diff vs. previous snapshot** — once the daily history accumulates, each
  total shows the change since yesterday.

### Trade finder

For your roster, the trade finder surfaces 1-for-1, 2-for-1, 1-for-2, and
2-for-2 trade candidates with each opposing team. A candidate is shown when
**each team improves on either dimension** — optimal starting lineup *or*
total dynasty asset value — and FantasyCalc value parity stays within
20% per side.

Draft picks are first-class tradeable assets: pick values come from
FantasyCalc and ownership comes from Sleeper's `traded_picks` endpoint
(applied to the league's default pick allocation). Picks slot into the
dynasty-asset half of the scoring, so trades that swap aging vets for
future picks (or vice versa) appear naturally.

Results are surfaced in tiers:

- **Highest Mutual Benefit** — both teams' lineups improve.
- **Convert futures to win-now** — you send picks/youth, get production.
- **Sell for picks** — you send production, get picks/youth.
- **Package deals** — multi-player trades (2-for-1, 1-for-2, 2-for-2).
- **By opposing team** — collapsible accordion with top candidates per partner.

### Waiver wire

Compares your roster to every player not rostered in your league and
surfaces:

- **🔥 Trending Adds** — Sleeper's community 24-hour add count, filtered
  to players still available in your league. Strongest early signal for
  what's actually moving on waiver wire.
- **Best Available Overall** — top dynasty-value free agents (excluding
  draft picks).
- **Targeted at gap positions** — best free agents at positions where
  your starting lineup ranks in the bottom third of the league.
- **Drop candidates** — your lowest-value skill players.

Each pickup gets a suggested drop matched by position eligibility.

## Roadmap

- **Projection swap-in** — replace FantasyCalc redraft values with
  ESPN/FantasyPros 2026 statistical projections when those land in late July.
- **News + usage signals** — surface injury status and ascending-usage
  flags (snap share trend, target share) per player.
- **Win-Now trade analysis** — currently the trade finder uses dynasty
  values as canonical trade-market currency. A Win-Now trade mode would
  optimize for this-season lineup gains.
- **Smarter drop suggestions** — currently the suggested drop is always
  the lowest-value compatible player. Could improve by matching position
  more carefully and rotating through multiple options.

## Add your league

1. Open [`leagues.yml`](leagues.yml).
2. Append your league:
   ```yaml
   - league_id: "your-sleeper-league-id"
     slug: "kebab-case-name"
     display_name: "League Display Name"
     my_user_id: "your-sleeper-user-id"   # optional, enables trade finder
   ```
3. Open a pull request. After merge, the nightly Action publishes a
   report at `/leagues/<slug>/`.

Your Sleeper league ID is the long number in the league URL:
`https://sleeper.com/leagues/<league_id>/...`. Your user ID is at
`https://api.sleeper.app/v1/user/<your-username>`.

## Local development

```bash
pip install -r pipeline/requirements.txt
python pipeline/generate.py
python -m http.server 8765 --directory site
# open http://localhost:8765
```

API responses are cached to `cache/` with TTLs (Sleeper player DB: 24h,
league/rosters: 1h, FantasyCalc values: 24h) so re-runs are fast.

## Architecture

```
pipeline/         Python — data fetch, lineup math, HTML rendering
  data.py           Sleeper + FantasyCalc clients with file cache
  lineup.py         Optimal-lineup calculator (greedy under slot constraints)
  trades.py         Trade finder (1v1/2v1/1v2/2v2 + picks + asset/lineup scoring)
  waivers.py        Waiver wire recommender (trending + value + gap-targeting)
  generate.py       Entry point: builds site/ and history/
  templates/        Jinja2 templates + CSS + toggle JS
site/             Published to GitHub Pages
history/          Daily JSON snapshots, git-tracked
leagues.yml       Which leagues to build
.github/workflows/refresh.yml   Nightly Action
```

## Methodology notes

- **Value source.** [FantasyCalc](https://fantasycalc.com) — both dynasty
  (`value`) and redraft (`redraftValue`) come from the same response.
  Dynasty values reflect multi-year expected production with age weighting;
  redraft values reflect this-season-only expected production.
- **Lineup optimization.** Greedy assignment from most-restrictive slots
  outward. Optimal because FLEX is a strict superset of the positions it
  draws from; there's no scenario where reserving a higher-value player
  for FLEX beats placing it in a position-locked slot first.
- **Exclusions.** Taxi-squad and IR players are excluded from the optimal
  lineup pool.
- **K and DEF.** FantasyCalc doesn't value kickers or team defenses, so
  these display value 0. The omission has negligible impact on
  league valuation.

## Data sources

- [Sleeper API](https://docs.sleeper.com) — free, no auth, league + roster data
- [FantasyCalc API](https://api.fantasycalc.com) — free, no auth, trade values

## License

MIT
