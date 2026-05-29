"""Partner-impact pitch generator.

For each trade candidate, produce a 1-2 sentence human explanation of why
the *partner* would accept it — framed around their roster needs and timeline,
not abstract dynasty points. Pure templating over data we already compute:
the partner's per-position strength (gap/surplus/average) and their
trajectory (win-now / rebuild / balanced).
"""
from __future__ import annotations

import re

from data import Player
from trades import is_aging_vet

SKILL_ORDER = ["QB", "RB", "WR", "TE"]
TRAJECTORY_THRESHOLD = 2

TRAJECTORY_PHRASE = {
    "win-now": "competing now",
    "rebuild": "rebuilding",
    "balanced": "balanced",
}

_PICK_SLOT_RE = re.compile(r"(\d{4})\s+(\d+)\.(\d+)")
_PICK_RE = re.compile(r"(\d{4})\s+R(\d+)")
_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}


def _trajectory(dynasty_rank: int, winnow_rank: int) -> str:
    delta = dynasty_rank - winnow_rank
    if delta > TRAJECTORY_THRESHOLD:
        return "win-now"
    if delta < -TRAJECTORY_THRESHOLD:
        return "rebuild"
    return "balanced"


def _asset_label(p: Player) -> str:
    """Clean label for a player or pick. '2026 1.10 (Foo)' -> '2026 1.10';
    '2026 R1 (Foo)' -> '2026 1st'."""
    if p.position == "PICK":
        name = p.name or ""
        m = _PICK_SLOT_RE.search(name)
        if m:
            return f"{m.group(1)} {int(m.group(2))}.{int(m.group(3)):02d}"
        m = _PICK_RE.search(name)
        if m:
            year, rnd = m.group(1), int(m.group(2))
            return f"{year} {_ORDINAL.get(rnd, str(rnd) + 'th')}"
    return p.name


def _names(players: list[Player]) -> str:
    names = [_asset_label(p) for p in players]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _verb(players: list[Player], singular: str, plural: str) -> str:
    return singular if len(players) == 1 else plural


def build_partner_pitch(
    send: list[Player],          # players the PARTNER receives
    receive: list[Player],       # players the PARTNER gives up
    partner_name: str,
    partner_strength: dict,      # {pos: {value, league_rank, label}} (dynasty)
    dynasty_rank: int,
    winnow_rank: int,
    num_teams: int,
    trajectory_override: str | None = None,
) -> str:
    # Callers (e.g. the trade-target timeline override) can force a timeline;
    # otherwise infer it from the rank spread.
    trajectory = trajectory_override or _trajectory(dynasty_rank, winnow_rank)

    in_skill = [p for p in send if p.is_skill]
    in_picks = [p for p in send if p.position == "PICK"]
    out_skill = [p for p in receive if p.is_skill]

    # A rebuilder doesn't value an aging vet as a positional "fill" — they're
    # acquiring for the future. Exclude over-cliff vets from the fit framing so
    # the pitch never sells a 32-year-old as filling a rebuild's gap.
    fit_skill = (
        [p for p in in_skill if not is_aging_vet(p)]
        if trajectory == "rebuild" else in_skill
    )

    clauses: list[str] = []

    # 1. Position fit for the skill players the partner receives.
    gap_fit = None
    depth_fit = None
    for pos in SKILL_ORDER:
        at_pos = [p for p in fit_skill if p.position == pos]
        if not at_pos:
            continue
        info = partner_strength.get(pos, {})
        label = info.get("label")
        if label == "gap" and gap_fit is None:
            gap_fit = f"{_names(at_pos)} {_verb(at_pos, 'fills', 'fill')} their {pos} gap (#{info.get('league_rank')} of {num_teams})"
        elif depth_fit is None and label != "surplus":
            depth_fit = f"{_names(at_pos)} {_verb(at_pos, 'upgrades', 'upgrade')} their {pos}"

    if gap_fit:
        clauses.append(gap_fit)
    elif depth_fit:
        clauses.append(depth_fit)
    elif in_skill and trajectory == "win-now":
        clauses.append(f"{_names(in_skill)} {_verb(in_skill, 'adds', 'add')} proven production for their playoff push")
    elif fit_skill:
        clauses.append(f"they land {_names(fit_skill)}")

    # 2. Picks the partner receives — frame as cashing in the outgoing star,
    #    or as future capital for a rebuild.
    if in_picks:
        if out_skill:
            star = max(out_skill, key=lambda p: p.dynasty_value)
            phrase = "flip" if trajectory == "win-now" else "cash in"
            clauses.append(f"they {phrase} {star.name} for {_names(in_picks)}")
        elif trajectory == "rebuild":
            clauses.append(f"{_names(in_picks)} adds future capital for their rebuild")
        else:
            clauses.append(f"they pick up {_names(in_picks)}")

    # 3. Spare note: dealing a skill player from a surplus position.
    spare = None
    for pos in SKILL_ORDER:
        at_pos = [p for p in out_skill if p.position == pos]
        if at_pos and partner_strength.get(pos, {}).get("label") == "surplus":
            spare = f"dealing from their {pos} surplus"
            break

    if not clauses:
        return ""

    body = _cap(clauses[0])
    for extra in clauses[1:]:
        body += "; " + extra
    if spare and "surplus" not in body:
        body += f", {spare}"
    body += "."

    return f"{partner_name} is {TRAJECTORY_PHRASE[trajectory]}. {body}"
