"""News feed for rostered players.

Pulls ESPN's NFL news, filters to articles mentioning players actually
rostered in the league, scores each article by how likely it is to move
player value (keyword-weighted), and sorts by impact then recency.

The goal: a Josh Jacobs arrest should outrank a Trevor Lawrence haircut
even if the haircut headline is newer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from data import Player

TOP_NEWS_ITEMS = 10

# Score thresholds. Headline+description text is scanned for these keywords;
# weights below sum into an importance score. A player-value multiplier
# scales the final score by how valuable the affected player is.
HIGH_IMPACT_KEYWORDS = {
    # Injuries / health
    "injur", "surgery", "knee surgery", "shoulder surgery",
    "torn", "acl", "mcl", "achilles",
    "concussion", "concussed", "concussion protocol",
    "fracture", "broken", "strain",
    "season-ending", "out for season", "out for the season",
    "placed on ir", "placed on injured reserve", "ir-",
    "ruled out", "doubtful", "limited in practice",
    "concerned about", "availability concerns",
    # Discipline / off-field
    "arrest", "suspended", "suspension", "indefinitely",
    "investigation", "domestic violence", "dui",
    # Career-altering moves
    "fired", "released", "cut by", "waived",
    "season debut", "activated from ir",
}
MEDIUM_IMPACT_KEYWORDS = {
    "trade", "traded", "signed with", "signs with",
    "extension", "deal with", "contract dispute", "holdout",
    "benched", "demoted", "promoted", "depth chart",
    "starting", "starter", "named starter", "first-team",
    "active for", "inactive",
}
LOW_IMPACT_KEYWORDS = {
    # Personal life — usually doesn't move value
    "family", "wife", "husband", "child", "baby", "newborn",
    "welcome first", "welcome second",
    "wedding", "married", "engaged",
    "vacation", "offseason routine", "social media",
    # Lifestyle fluff
    "haircut", "tattoo", "instagram", "twitter post",
    "charity event", "foundation",
    # Generic preview-y stuff
    "perfect fit", "perfect pairing", "second year",
    "could improve", "ready to",
}

HIGH_WEIGHT = 30
MEDIUM_WEIGHT = 15
LOW_PENALTY = -10

# Player-value tiers boost the score for news about more valuable players.
ELITE_VALUE_THRESHOLD = 8000   # top ~25 dynasty
STARTER_VALUE_THRESHOLD = 4000  # top ~50-75 dynasty

# Display threshold: items with score >= this get a visual high-impact badge.
HIGH_IMPACT_BADGE_THRESHOLD = 30


@dataclass
class NewsItem:
    headline: str
    description: str
    url: str | None
    published: str
    age_hours: float
    matched_players: list[Player]
    importance_score: int


def _published_to_age_hours(published: str | None) -> float:
    if not published:
        return 9999.0
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600.0
    except (ValueError, TypeError):
        return 9999.0


def _base_score(text: str) -> int:
    """Score the text alone, ignoring player value. Higher = more impactful."""
    t = text.lower()
    score = 0
    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in t:
            score += HIGH_WEIGHT
    for kw in MEDIUM_IMPACT_KEYWORDS:
        if kw in t:
            score += MEDIUM_WEIGHT
    for kw in LOW_IMPACT_KEYWORDS:
        if kw in t:
            score += LOW_PENALTY
    return score


def _player_value_multiplier(player: Player) -> float:
    if player.dynasty_value >= ELITE_VALUE_THRESHOLD:
        return 1.5
    if player.dynasty_value >= STARTER_VALUE_THRESHOLD:
        return 1.2
    return 1.0


def _importance_score(text: str, players: list[Player]) -> int:
    """Combined score: text keywords × best-affected-player value tier.
    Floor at 0 so 'fun news about a star' doesn't outrank silence."""
    base = _base_score(text)
    if not players:
        return max(0, base)
    best_multiplier = max((_player_value_multiplier(p) for p in players), default=1.0)
    return max(0, int(base * best_multiplier))


def build_news_feed(
    articles: list[dict],
    rostered_players_by_espn_id: dict[str, Player],
) -> list[dict]:
    """Filter articles to ones mentioning rostered players, score them, and
    sort by impact then recency."""
    items: list[NewsItem] = []
    seen_headlines: set[str] = set()
    for art in articles:
        headline = art.get("headline") or ""
        if headline in seen_headlines:
            continue

        matched: list[Player] = []
        seen_sleeper_ids: set[str] = set()
        for cat in art.get("categories") or []:
            if cat.get("type") != "athlete":
                continue
            ath = cat.get("athlete") or {}
            espn_id = str(ath.get("id")) if ath.get("id") else None
            if not espn_id:
                continue
            p = rostered_players_by_espn_id.get(espn_id)
            if p and p.sleeper_id not in seen_sleeper_ids:
                matched.append(p)
                seen_sleeper_ids.add(p.sleeper_id)

        if not matched:
            continue

        seen_headlines.add(headline)
        text = headline + " " + (art.get("description") or "")
        score = _importance_score(text, matched)

        items.append(NewsItem(
            headline=headline,
            description=art.get("description") or "",
            url=(art.get("links") or {}).get("web", {}).get("href"),
            published=art.get("published") or "",
            age_hours=_published_to_age_hours(art.get("published")),
            matched_players=matched,
            importance_score=score,
        ))

    # Sort by importance desc, then by recency (newer first).
    items.sort(key=lambda i: (-i.importance_score, i.age_hours))
    return [_to_dict(i) for i in items[:TOP_NEWS_ITEMS]]


def _to_dict(i: NewsItem) -> dict:
    return {
        "headline": i.headline,
        "description": i.description,
        "url": i.url,
        "published": i.published,
        "age_hours": round(i.age_hours, 1),
        "importance_score": i.importance_score,
        "high_impact": i.importance_score >= HIGH_IMPACT_BADGE_THRESHOLD,
        "players": [
            {
                "sleeper_id": p.sleeper_id,
                "name": p.name,
                "position": p.position,
                "team": p.team,
                "dynasty_value": p.dynasty_value,
            }
            for p in i.matched_players
        ],
    }
