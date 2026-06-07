# Idea bank

Captured ideas not yet built. Sorted by priority. Update freely as ideas land
or change priority.

## Legend

- **Effort**: XS (under 1 hr) · S (1–3 hrs) · M (half-day) · L (full day or more)
- **Impact**: H (changes daily use, big UX or signal jump) · M (noticeable improvement) · L (polish, marginal)
- **Priority**: P0 (do soon) · P1 (do next) · P2 (later, often blocked on season/data) · P3 (nice-to-have)

> **All P0s shipped** as of this pass — partner-impact pitch, per-team
> trajectory awareness, and smarter waiver drops. P1 is now the top of the
> stack.

> **External review triage (2026-05).** A reviewer scored the project
> Concept 8 / Tech 7.5 / **UI-UX 5.5** / Differentiation 7, growth "high."
> Most of it evaluated the public **landing page** and underrates the depth
> already inside league pages (trade targets + timeline override, partner
> pitches, power rankings, news scoring, draft boards, compare). The valid,
> high-leverage core: the **front door doesn't show what's behind it**, and
> the product reads "data tool" more than "opinionated assistant." Net-new
> items added below: landing hero + showcase, roster diagnosis narrative,
> weekly auto-digest, explain-the-why, design polish, plus P3 (tiered
> rankings, chat assistant, draft simulator, branding, methodology hub).
> Already-covered review points mapped to existing rows: "league import" →
> client-side input, "trade analyzer" → negotiation sandbox, "cross-league
> portfolio" → multi-league. "Team direction" framing already exists as the
> win-now/balanced/rebuild trajectory tags — the gap is *prose*, folded into
> roster diagnosis.

## Priority matrix

| Pri | Idea | Effort | Impact | Notes |
|---|---|---|---|---|
| P1 | Trade negotiation sandbox | M | M | "Paste in a trade, see the verdict" (review: "trade analyzer") |
| P1 | Usage trends from nflverse | L | H | Only real "alpha" data source on the list |
| P1 | Landing page with client-side league input | M | H | Any visitor drops in a league ID, sees a report (review: "league import") |
| P2 | ESPN / FantasyPros projection swap-in | S | H | Blocked on data — publishes late July |
| P2 | Start/sit recommendations | M | H | In-season only |
| P2 | Bye-week awareness on lineups + waivers | S | M | In-season only |
| P2 | Player profile pages with history | M | M | Pays off as snapshots accumulate |
| P2 | Roster age distribution chart per team | S | M | Quick "is this roster aging?" signal |
| P2 | Global player search / filter | M | M | Cross-page utility |
| P2 | Single-owner generated output (stop double-committing docs/) | S | M | Kills rebase friction + the CI push-race failure class |
| P2 | Weekly auto-digest (risers / overvalued / holes / trade ops) | M | H | Synthesize a sticky summary from data we already have |
| P2 | Explain the "why" behind calls (age cliffs, scarcity) | S | M | Trust signal — attach reasoning to buy/sell/hold |
| P2 | Design polish pass (tier colors, wider tables on mobile) | S | M | Landing hierarchy + mobile rankings table DONE; tier colors + trades/compare mobile remain |
| P3 | Dark/light mode toggle | XS | L | System auto already works |
| P3 | Per-league OG card images | S | L | One generic image already does the job |
| P3 | Trade activity feed (across the league) | M | M | Sleeper exposes this; add only if a real use case shows up |
| P3 | Trade equity tracking over time | M | L | Needs months of history before it says anything |
| P3 | Multi-league support per user | L | M | Defer until someone outside our league uses it; unblocks cross-league exposure (review) |
| P3 | Fleaflicker / multi-platform support | L | M | Second data adapter; hard part is the player-name join to FantasyCalc + ESPN |
| P3 | Notifications (Discord / email) | L | L | Premature — open the site instead |
| P3 | Tiered player rankings view | S | M | Visual tiers + colors on rankings/values |
| P3 | Mock draft: trajectory bias | S | M | Tilt picks by team trajectory once we see how the model lands during draft season |
| P3 | AI chat assistant over league data | L | M | NL Q&A — needs a hosted endpoint, breaks static-only |
| P3 | Rookie draft simulator | L | M | Mock the rookie draft against the need-adjusted board |
| P3 | Branding / visual identity (name, logo, palette) | S | L | Dark mode + trajectory badges already exist |
| P3 | Data sources & methodology hub | XS | L | Consolidate trust signals now scattered in footers |

---

## Detailed entries

### ~~Partner-impact pitch language~~ — SHIPPED

Done in `pipeline/pitch.py`. Every trade card carries a "How to pitch it"
line framed around the partner's gaps, trajectory, and pick/youth angle.

### ~~Per-team trajectory awareness in trade evaluation~~ — SHIPPED

Done. `find_trades()` takes `my_value_fn` + `their_value_fn`; the partner's
lineup is judged under their trajectory (win-now → redraft, rebuild/balanced
→ dynasty). The toggle is now "my lens"; the partner's side is fixed by their
inferred timeline. Trade cards annotate "Their lineup (win-now/dynasty)".
Follow-up DONE: a rebuild partner now discounts aging vets it would *receive*
(`VET_CLIFF_AGE` × `REBUILD_VET_RETAINED` in `trades.py`), so we no longer
suggest dumping an old vet on a rebuilder, and the pitch never frames an
over-cliff vet as a positional "fill" for a rebuild (pitch.py uses the shared
`is_aging_vet`). Applies to both the acquisition flow and the trade finder.

### ~~Tier-classification purity~~ — SHIPPED

Done in `trades.py::_classify`. "buy"/"sell" now require the pick side to be
*predominantly* picks by dynasty value (`PREDOMINANTLY_PICKS = 0.6`), so a
pick + an established star going out is no longer a "buy" — it falls through
to "package" as a reshape. Verified: every buy has `pick_value_share(send)
>= 0.6`, every sell `>= 0.6` on receive; e.g. "send CMC + Meyers → Caleb
Williams + 2026 R1" (receive pick share 0.49) now lands in package, not sell.
Template tier blurbs updated to say "mostly picks." Left "reshape" as a
possible future sub-tier; routing to "package" avoided UI churn.

### ~~Slot-aware draft pick values (known seasons)~~ — SHIPPED

Done. When a season's Sleeper draft has a locked LINEAR order
(`data.draft_slots_by_season`), each pick is valued at its exact slot via
FantasyCalc `pick_slot_values` instead of the round average — so a 2026 1.01
(7,321) is worth ~2.9× a 1.10 (2,551), and a contender's late 1st no longer
equals a rebuilder's early 1st. Seasons with no draft created yet (2027+)
keep the discounted round-average fallback. Picks display their slot
("2026 1.10") when known, round ("2027 R1") otherwise; pitch labels handle
both. Flows through trades, targets, rankings, and asset value.

### ~~Filter implausible like-for-like trades~~ — SHIPPED

Done in `trades.py::_is_implausible_lateral`, applied during `find_trades`
enumeration. Same position multiset on both sides + no matched pair with a
≥4-yr age gap or >25% dynasty-value gap → dropped (a wash). Differing
multisets are kept (real positional shifts). Verified zero lateral washes
leak into any tier across both modes; mutual-tier reshapes with a clear
value/age story still survive. Not applied to acquisition packages (there the
user has explicitly chosen the target).

### ~~Smarter drop suggestions on waivers~~ — SHIPPED

Done. `_drop_candidates_for` now excludes optimal-lineup starters and
prioritizes same-position non-starters (drop a QB for a QB), falling back to
the lowest-value bench overall. Three options shown per pickup.

### ~~Hub grouping + left-hand nav~~ — SHIPPED

Done. Persistent left sidebar grouped into Overview / League & Projections /
Trade Center / Roster / Draft Prep, with active-page highlight and an
in-sidebar section list. Collapses to a top bar on mobile. Future hubs/pages
slot into `_nav.html.j2` with a one-line edit.

### ~~Player-targeted trade hub~~ — SHIPPED

Done. `/targets/` page under Trade Center: the players who'd most lift my
optimal lineup (`find_acquisition_packages` in trades.py), each with 1–3
acquisition packages judged for partner-acceptance under their timeline,
plus a pitch. Possible follow-ups: a balancing throw-in coming back, a
free-text "I want player X" picker, and win-now-mode targeting.

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

### Mock draft: trajectory bias &mdash; P3 · S · M

The mock draft (`draft.py::build_mock_draft`) scores rookies by
`dynasty_value × position-need multiplier` — best-player-available with a
positional lean. It does not bias by team trajectory: in rookie drafts
everyone's young, so position need was the cleanest first-cut signal.

If during real draft season we see managers picking systematically differently
based on trajectory, layer in:
- **Win-now teams** prefer rookies with higher `redraft_value` (immediate
  contributors) — blend a small fraction of redraft into the score.
- **Rebuild teams** prefer upside — boost rookies whose dynasty value is
  notably higher than their redraft value (longer runway).

Wait for live signal before tuning; the current model is honest and easy to
reason about.

### Fleaflicker / multi-platform support &mdash; P3 · L · M

Today everything is Sleeper-only: `data.py` hits `api.sleeper.app` for
rosters, users, traded picks, drafts, and the player DB, and `leagues.yml`
takes a Sleeper `league_id`. Fleaflicker has a public read-only JSON API
(`https://www.fleaflicker.com/api/...`, no auth for public leagues) exposing
standings, rosters, trades, and draft data, so it's feasible as a second
adapter.

Scope:
- New Fleaflicker client mirroring the Sleeper fetchers, plus a
  `platform: sleeper|fleaflicker` field in `leagues.yml` to dispatch.
- **Hard part — the value/news join.** FantasyCalc values are keyed on
  Sleeper IDs / names and the `Player` model leans on `sleeper_id` + `espn_id`
  throughout. Fleaflicker uses its own player IDs, so players must be matched
  by **name** (+ team/position tiebreakers) to FantasyCalc and ESPN news.
  Name-matching edge cases (Jr./II, "D.J." vs "DJ", recently-traded teams)
  are where the real work is.
- Picks/draft order differ from Sleeper's `traded_picks` + `/drafts`, so the
  pick-ownership + slot-aware valuation need a Fleaflicker equivalent.

Everything downstream (lineup solver, trades, targets, diagnosis, rankings,
pitches) is platform-agnostic once a league is expressed as
`{players, owners, picks}` — the work is almost entirely the adapter + the ID
join. Verify against a real public Fleaflicker league before building.

### Notifications (Discord / email) &mdash; P3 · L · L

Push alerts when team value changes significantly, or when a trending
add becomes available. Premature — opening the site is fine until proven
otherwise.

---

## From the external review (2026-05)

### ~~Landing page hero + feature showcase~~ — SHIPPED

Done. `landing.html.j2` now leads with a hero (value prop + "See a live
example" CTA + a trust line on live Sleeper/FantasyCalc data) and a
feature-card grid linking into each tool of the example league. Replaced the
bare league list. Pairs with the still-open client-side league-input row.

### ~~Roster diagnosis — team-direction narrative~~ — SHIPPED

Done in `diagnosis.py`. A 2–4 sentence opinionated read per team: direction
(contender/rebuild via standing × trajectory), strongest position, soft
spot, an aging-anchor callout (position-aware cliff ages — a 30-yo QB isn't
flagged), and one next move. Pure templating like `pitch.py`. Surfaced as a
card atop the league overview (my team) and as prose under every team on
power rankings, with color-coded direction badges. This also covers the
review's "smarter recommendation text" and "team direction engine."

### Weekly auto-digest &mdash; P2 · M · H

A synthesized weekly summary — the stickiness play. All inputs already
exist; this is selection + phrasing:
- Biggest riser / faller (history deltas, or news-feed impact once usage
  trends land).
- Most overvalued / undervalued asset on my roster (value vs. lineup
  contribution).
- Top roster weakness (position gap).
- One or two live trade opportunities (pull from existing finder/targets).

Render as a panel on the league overview; later this is the natural payload
for the Notifications idea.

### Explain the "why" behind calls &mdash; P2 · S · M

Trust signal. Attach a short reason to buy/sell/hold and to target/avoid
calls, grounded in heuristics rather than just value numbers — e.g. RB
production-cliff age bands, positional scarcity, depth behind a starter.
Small, mostly a reasoning-string layer over data we have; complements the
roster diagnosis above.

### Design polish pass &mdash; P2 · S · M (partially done)

Reviewer rated UI/UX lowest. League pages are already carded with a sidebar,
trajectory badges, and good/bad color coding, so this is targeted, not a
rebuild:
- ~~Landing page hierarchy~~ — DONE via the hero + feature grid.
- ~~Power rankings table on mobile~~ — DONE: metric columns hidden ≤640px,
  `.table-scroll` safety net, direction badge wraps; no page overflow at 375px.
- Consistent tier colors / badges across rankings and values — still open.
- Mobile QA on the remaining wide tables (trades sides, compare) — still open.

### P3 grab-bag from the review

- **Tiered player rankings view** (S/M): visual tier breaks + color on
  rankings/values, the way managers actually think about players.
- **AI chat assistant** (L/M): natural-language Q&A over league data. Note:
  needs a hosted inference endpoint + key — breaks the static-only, zero-cost
  model, so it's a deliberate architecture decision, not a quick add.
- **Rookie draft simulator** (L/M): mock the rookie draft against the
  need-adjusted board we already build in `draft.py`.
- **Branding / visual identity** (S/L): a real name, logo, and palette. Dark
  mode + trajectory badges already exist; this is identity polish.
- **Data sources & methodology hub** (XS/L): one page consolidating the
  trust signals currently scattered across page footers (Sleeper,
  FantasyCalc, how values + lineups are computed).
- **Cross-league player exposure**: blocked on multi-league support; once a
  user has >1 league, "how much Bijan do I have across all of them?" is a
  genuinely underserved feature.
