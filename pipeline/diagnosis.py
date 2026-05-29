"""Roster diagnosis — a short, opinionated read on each team.

Pure templating over signals we already compute: dynasty / win-now standing,
per-position strength (gap / surplus), starter ages, and pick capital. Turns
the dashboard into an assistant by stating a *direction* and a *next move*, the
way a manager actually talks about their roster. Same approach as pitch.py.

Offseason note: with no game results yet, "contender / rebuild" is read from
roster value (dynasty rank) and the dynasty-vs-winnow spread, not record.
"""
from __future__ import annotations

SKILL = ("QB", "RB", "WR", "TE")
TRAJECTORY_THRESHOLD = 2

# Age at which a *starter* becomes a "clock" risk worth calling out by name.
# Position-aware: RBs fall off early, QBs play deep into their 30s, so a 30-yo
# QB is in his prime — not someone to sell.
CLIFF_AGE = {"RB": 28, "WR": 30, "TE": 31, "QB": 35}
DEFAULT_CLIFF_AGE = 30
YOUNG_CORE_AVG = 25.0

# Standing tertile (by dynasty rank) × trajectory → short direction label.
DIRECTION = {
    ("top", "win-now"): "Win-now contender",
    ("top", "balanced"): "Balanced contender",
    ("top", "rebuild"): "Contender built to last",
    ("middle", "win-now"): "Pushing to contend",
    ("middle", "balanced"): "Middle of the pack",
    ("middle", "rebuild"): "Young and rising",
    ("bottom", "win-now"): "Veteran-heavy, outside the tier",
    ("bottom", "balanced"): "Rebuilding",
    ("bottom", "rebuild"): "Full rebuild",
}


def _tertile(rank: int, n: int) -> str:
    """'top' / 'middle' / 'bottom' third by rank (1 = best)."""
    third = max(1, round(n / 3))
    if rank <= third:
        return "top"
    if rank > n - third:
        return "bottom"
    return "middle"


def _trajectory(dynasty_rank: int, winnow_rank: int) -> str:
    delta = dynasty_rank - winnow_rank
    if delta > TRAJECTORY_THRESHOLD:
        return "win-now"
    if delta < -TRAJECTORY_THRESHOLD:
        return "rebuild"
    return "balanced"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def build_team_diagnosis(
    team_name: str,
    dynasty_rank: int,
    winnow_rank: int,
    num_teams: int,
    position_strength: dict,        # {pos: {value, league_rank, label}} (dynasty)
    starters: list[dict],           # dynasty optimal-lineup player dicts
    pick_count: int = 0,
    pick_value: int = 0,
) -> dict:
    """Return a structured diagnosis: a direction label plus a 2–4 sentence
    prose summary, and the raw signals for any UI badges."""
    standing = _tertile(dynasty_rank, num_teams)
    trajectory = _trajectory(dynasty_rank, winnow_rank)
    direction = DIRECTION[(standing, trajectory)]

    # Strengths and gaps, picking the most extreme by league rank.
    surplus = [p for p in SKILL if position_strength.get(p, {}).get("label") == "surplus"]
    gaps = [p for p in SKILL if position_strength.get(p, {}).get("label") == "gap"]
    top_pos = min(surplus, key=lambda p: position_strength[p]["league_rank"]) if surplus else None
    gap_pos = max(gaps, key=lambda p: position_strength[p]["league_rank"]) if gaps else None

    # Starter ages → average and aging anchors worth a callout.
    ages = [
        (s.get("name"), s.get("position"), s.get("age"))
        for s in starters
        if s.get("position") in SKILL and s.get("age")
    ]
    avg_age = round(sum(a for _, _, a in ages) / len(ages), 1) if ages else None
    anchors = [
        (name, pos, age) for name, pos, age in ages
        if age >= CLIFF_AGE.get(pos, DEFAULT_CLIFF_AGE)
    ]
    anchors.sort(key=lambda x: -x[2])

    sentences: list[str] = []

    # 1. Standing + timeline.
    s1 = f"{team_name} ranks {_ordinal(dynasty_rank)} of {num_teams} in dynasty value"
    if trajectory == "win-now":
        s1 += f", and rises to {_ordinal(winnow_rank)} win-now — a veteran-leaning roster."
    elif trajectory == "rebuild":
        s1 += f", but sits {_ordinal(winnow_rank)} win-now — young and still maturing."
    else:
        s1 += "."
    sentences.append(s1)

    # 2. Strength / gap shape.
    if top_pos and gap_pos:
        sentences.append(
            f"{top_pos} is a strength ({_ordinal(position_strength[top_pos]['league_rank'])} "
            f"of {num_teams}), while {gap_pos} is the soft spot "
            f"({_ordinal(position_strength[gap_pos]['league_rank'])})."
        )
    elif top_pos:
        sentences.append(
            f"{top_pos} leads the way ({_ordinal(position_strength[top_pos]['league_rank'])} "
            f"of {num_teams}) with no glaring hole elsewhere."
        )
    elif gap_pos:
        sentences.append(
            f"{gap_pos} is the clear soft spot "
            f"({_ordinal(position_strength[gap_pos]['league_rank'])} of {num_teams})."
        )
    else:
        sentences.append("The roster is balanced across positions.")

    # 3. Age signal — only when there's something worth saying.
    if anchors:
        a = anchors[0]
        extra = f" and {len(anchors) - 1} other aging starter{'s' if len(anchors) - 1 != 1 else ''}" if len(anchors) > 1 else ""
        sentences.append(f"Watch the clock: {a[0]} ({a[2]}){extra} anchor{'s' if not extra else ''} the lineup.")
    elif avg_age is not None and avg_age <= YOUNG_CORE_AVG:
        sentences.append(f"The starting core is young (avg age {avg_age}) — time is on your side.")

    # 4. One actionable nudge.
    if standing == "top":
        if gap_pos:
            nudge = f"Lean in — turn depth or picks into an upgrade at {gap_pos}."
        else:
            nudge = "Lean in — consolidate depth into a difference-maker while you're built to win."
    elif trajectory == "rebuild" or standing == "bottom":
        body = "keep stacking youth and picks"
        if anchors:
            body += f"; cash {anchors[0][0]} while the value holds"
        if pick_count >= 4:
            body += f" (you already hold {pick_count} picks worth {pick_value:,})"
        nudge = _cap(body) + "."
    else:
        nudge = (
            f"A targeted move at {gap_pos} could tip you toward contention."
            if gap_pos else
            "A targeted upgrade could push you into the top tier."
        )
    sentences.append(nudge)

    return {
        "direction": direction,
        "trajectory": trajectory,
        "standing": standing,
        "strength_pos": top_pos,
        "gap_pos": gap_pos,
        "avg_age": avg_age,
        "summary": " ".join(sentences),
    }
