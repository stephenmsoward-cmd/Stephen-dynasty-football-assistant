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
| P0 | Partner-impact pitch language on trades | S | H | Pure templating over data we already have |
| P0 | Smarter drop suggestions on waivers | S | M | Position-matched drops, rotate candidates |
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
| P3 | Dark/light mode toggle | XS | L | System auto already works |
| P3 | Per-league OG card images | S | L | One generic image already does the job |
| P3 | Trade activity feed (across the league) | M | M | Sleeper exposes this; add only if a real use case shows up |
| P3 | Trade equity tracking over time | M | L | Needs months of history before it says anything |
| P3 | Multi-league support per user | L | M | Defer until anyone outside our league actually uses it |
| P3 | Notifications (Discord / email) | L | L | Premature — open the site instead |

---

## Detailed entries

### Partner-impact pitch language &mdash; P0 · S · H

On every trade recommendation, render 1–2 lines explaining the trade's
impact to the *partner's* roster in human terms — what positional gap it
fills, what their trajectory benefits — rather than just the abstract
dynasty point delta.

We already have the underlying data: per-team `position_strength`,
trajectory labels (win-now / rebuild / balanced), and the player flow per
side. This is templating, not generation.

Example:
> "Fills Mongo's WR depth gap (their rank #7) with Burden's youth.
> The future 1st extends their rebuild window. You swap excess WR depth
> for a starting TE."

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
