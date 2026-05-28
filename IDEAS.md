# Idea bank

Captured ideas not yet built. Sorted by priority. Update freely as ideas land
or change priority.

## Legend

- **Effort**: XS (under 1 hr) · S (1–3 hrs) · M (half-day) · L (full day or more)
- **Impact**: H (changes daily use, big UX or signal jump) · M (noticeable improvement) · L (polish, marginal)
- **Priority**: P0 (do soon) · P1 (do next) · P2 (later, often blocked on season/data) · P3 (nice-to-have)

## Priority matrix

| Pri | Idea | Effort | Impact | Notes |
|---|---|---|---|---|
| P0 | Per-team trajectory awareness in trade eval | M | H | Score each side under their *own* timeline, not the user's toggle |
| P0 | Smarter drop suggestions on waivers | S | M | Position-matched drops, rotate candidates |
| P1 | Filter implausible like-for-like trades | S | M | A QB+RB→QB+RB swap with no age/value asymmetry is a no-deal |
| P1 | Hub grouping + left-hand nav | L | H | Architectural — pulls forward several other items |
| P1 | Player-targeted trade hub | M | H | Best inside a restructured Trade Center |
| P1 | Trade negotiation sandbox | M | M | "Paste in a trade, see the verdict" |
| P1 | Usage trends from nflverse | L | H | Only real "alpha" data source on the list |
| P1 | Landing page with client-side league input | M | H | Any visitor can drop in a league ID and see a report |
| P2 | ESPN / FantasyPros projection swap-in | S | H | Blocked on data — publishes late July |
| P2 | Start/sit recommendations | M | H | In-season only |
| P2 | Bye-week awareness on lineups + waivers | S | M | In-season only |
| P2 | Player profile pages with history | M | M | Pays off as snapshots accumulate |
| P2 | Roster age distribution chart per team | S | M | Quick "is this roster aging?" signal |
| P2 | Global player search / filter | M | M | Cross-page utility |
| P2 | Single-owner generated output (stop double-committing docs/) | S | M | Kills rebase friction + the CI push-race failure class |
| P3 | Dark/light mode toggle | XS | L | System auto already works |
| P3 | Per-league OG card images | S | L | One generic image already does the job |
| P3 | Trade activity feed (across the league) | M | M | Sleeper exposes this; add only if a real use case shows up |
| P3 | Trade equity tracking over time | M | L | Needs months of history before it says anything |
| P3 | Multi-league support per user | L | M | Defer until anyone outside our league actually uses it |
| P3 | Notifications (Discord / email) | L | L | Premature — open the site instead |

---

## Detailed entries

### ~~Partner-impact pitch language~~ — SHIPPED

Done in `pipeline/pitch.py`. Every trade card carries a "How to pitch it"
line framed around the partner's gaps, trajectory, and pick/youth angle.

### Per-team trajectory awareness in trade evaluation &mdash; P0 · M · H

Today the trade finder uses ONE value function (dynasty or win-now,
selected by the user) for BOTH teams' lineup recomputation. In reality
each manager evaluates trades by their own timeline:

- Win-now teams care about redraft-value lineup improvement
- Rebuild teams care about dynasty asset value (especially picks + youth)
- Balanced teams care about both

We already infer each team's timeline from the trajectory tag in
`rankings.py` (win-now / rebuild / balanced). Trade evaluation should
score each side using their trajectory's appropriate value function, not
the user's selected mode.

Concrete change:
- `find_trades()` accepts `my_value_fn` and `their_value_fn` separately
- The partner team's `their_value_fn` is chosen by their trajectory:
  - "win-now" → redraft_value
  - "rebuild" → dynasty_value (with extra weight on age + picks)
  - "balanced" → dynasty_value (current behavior)
- Tier classification (`mutual`, `buy`, `sell`) uses each side's
  trajectory-adjusted improvement, not raw values

This composes well with the partner-impact pitch (P0): once we know what
the partner *actually* wants, the pitch can say "Glass bones is in
rebuild mode; this trade fills their lineup gap AND nets them future
asset value" — much more believable than abstract lineup math.

### Filter implausible like-for-like trades &mdash; P1 · S · M

A QB + RB → QB + RB trade (or any same-position-multiset swap) is rarely
realistic unless there's meaningful age or quality asymmetry. If both
sides come out roughly equivalent at the same positions, neither manager
has a reason to pull the trigger.

Concrete heuristic:
1. Compute position multisets per side: `Counter([p.position for p in send])`
2. If multisets are equal:
   - Check per-position age difference between matched players
   - Check per-position dynasty-value difference
   - If neither shows asymmetry (e.g., >4 yr age gap or >25% value gap
     for at least one position pair) → demote out of mutual tier or
     drop entirely
3. If position multisets differ → keep as-is (it's a real positional shift)

Result: lateral swaps with no reason to happen disappear from the top
tiers; trades with clear "older for younger" or "depth for star" stories
remain.

### Smarter drop suggestions on waivers &mdash; P0 · S · M

Currently waiver pickups always suggest the lowest-value rostered skill
player as the drop candidate. Improve by:
- Matching drop position to pickup position when sensible (RB pickup →
  RB drop)
- Surfacing 2–3 candidates instead of always the same one
- Avoiding suggesting starters

### Hub grouping + left-hand nav &mdash; P1 · L · H

Group existing pages under thematic hubs with a persistent left-hand
sidebar:

| Hub | Pages |
|---|---|
| Draft Prep | Draft recs (+ later: rookie ADP, mock sims) |
| Trade Center | Trade finder, trade hub, sandbox |
| League Rankings / Projections | Standings, power rankings, compare |
| Roster Optimization | News, waivers, start/sit (future) |

Current "league landing" becomes a dashboard pulling key insights from
each hub. This is the architectural move that turns a flat page list into
a real product.

### Player-targeted trade hub &mdash; P1 · M · H

Pick a player you covet from another team; system surfaces trade packages
that would acquire them, ranked by what the partner would actually
accept.

The `find_trades` algorithm already accepts a tradeable pool. Add a
filter that requires the candidate's `receive` set to include a specific
target player. UI: target-player picker on the trades page (or inside
the restructured Trade Center).

### Trade negotiation sandbox &mdash; P1 · M · M

Let users paste in any proposed trade and immediately see the lineup
impact (both modes), asset value change, and a verdict from both sides.
Reuses all existing math; new feature is the UI for trade entry.

### Usage trends from nflverse &mdash; P1 · L · H

Pull weekly snap counts, target share, and route participation from
nflverse CSV releases. Surface ascending/declining player badges before
FantasyCalc values move. The closest thing to alpha — catches up-trending
players a week or two before the market re-prices them.

### Landing page with client-side league input &mdash; P1 · M · H

Anyone visiting the site can paste a Sleeper league ID and see a generated
report client-side (Sleeper + FantasyCalc are CORS-friendly). Turns the
project from "my dashboard" into "anyone's dashboard" — significantly
better portfolio piece.

### ESPN / FantasyPros statistical projections &mdash; P2 · S · H

Replace FC redraft values with real per-game stat projections once ESPN
or FantasyPros publish 2026 numbers in late July. Architecture already
supports the swap via `Player.redraft_value`. Just need a fetcher.

### Start/sit recommendations &mdash; P2 · M · H

Per-week lineup decisions with opponent matchup awareness. Requires
weekly schedule data + statistical projections. In-season feature.

### Bye-week awareness &mdash; P2 · S · M

Show bye weeks on lineups; flag stacked-bye risk on waiver pickups; help
plan in-season FAAB bids around byes. In-season only.

### Player profile pages &mdash; P2 · M · M

One page per player showing value history, news, usage trends, ownership
(rostered/free). Most useful once 30+ days of history have accumulated.

### Roster age distribution chart &mdash; P2 · S · M

Small visualization per team showing age curve of skill-position
starters. Quick "is this roster aging?" signal complementing the
trajectory tag.

### Single-owner generated output &mdash; P2 · S · M

Today both the local dev workflow and the nightly Action commit the
generated `docs/` + `history/` files. Because they touch the same files,
every local push collides with the Action's commits — resolved by hand
each time with `git checkout --theirs` + rebase. It's also the root of
the CI push-race failure (now mitigated by rebase-retry, but the friction
remains).

Pick ONE owner of the generated output:

- **Option A — Action is sole committer.** Add `docs/` and `history/` to
  `.gitignore`. Local dev builds into an untracked `docs/` for preview only.
  The Action regenerates and commits. Pages keeps deploying from `main /docs`.
  Pro: pushes never conflict. Con: deployed site only reflects committed
  source after the next Action run (no instant local-built deploy).

- **Option B — back to Pages-artifact deploy.** Gitignore `docs/`
  entirely; the Action builds and deploys via `upload-pages-artifact` +
  `deploy-pages` (the original setup). Requires Pages source = "GitHub
  Actions" and the Actions infra to be healthy (it was flaky once).

Option A is simpler and keeps the resilient branch-deploy we have now.

### Global player search / filter &mdash; P2 · M · M

Search box that finds any player (rostered or free agent) and links to
their profile. Filter the lineups / standings tables by name or
position.

### Dark/light mode toggle &mdash; P3 · XS · L

System auto-detection already works via CSS media queries. Explicit
toggle is polish — only worth it if a user requests overriding the
system default.

### Per-league OG card images &mdash; P3 · S · L

Generate `docs/leagues/<slug>/og.png` per league with the league name +
trajectory snapshot baked in. The generic image already does the job for
sharing.

### Trade activity feed &mdash; P3 · M · M

Sleeper exposes recent trade activity per league. Could surface a "what
got traded this week" panel. Add if it earns its keep against the noise.

### Trade equity tracking over time &mdash; P3 · M · L

Once daily history runs, track which manager "won" each trade by
comparing the two sides' value trajectories after the trade. Needs
months of data before it says anything reliable.

### Multi-league support per user &mdash; P3 · L · M

A user owns multiple leagues. Today each league is independent. Defer
until anyone outside our league actually uses the tool.

### Notifications (Discord / email) &mdash; P3 · L · L

Push alerts when team value changes significantly, or when a trending
add becomes available. Premature — opening the site is fine until proven
otherwise.
