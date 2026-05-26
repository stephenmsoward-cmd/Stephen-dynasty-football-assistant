"""News feed for rostered players.

Pulls ESPN's NFL news, filters to articles mentioning players actually
rostered in the league, and bubbles up the most recent ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from data import Player

TOP_NEWS_ITEMS = 10


@dataclass
class NewsItem:
    headline: str
    description: str
    url: str | None
    published: str
    age_hours: float
    matched_players: list[Player]


def _published_to_age_hours(published: str | None) -> float:
    if not published:
        return 9999.0
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600.0
    except (ValueError, TypeError):
        return 9999.0


def build_news_feed(
    articles: list[dict],
    rostered_players_by_espn_id: dict[str, Player],
) -> list[dict]:
    """Filter articles to ones mentioning rostered players, sorted by recency."""
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
        items.append(NewsItem(
            headline=headline,
            description=art.get("description") or "",
            url=(art.get("links") or {}).get("web", {}).get("href"),
            published=art.get("published") or "",
            age_hours=_published_to_age_hours(art.get("published")),
            matched_players=matched,
        ))

    items.sort(key=lambda i: i.age_hours)
    return [_to_dict(i) for i in items[:TOP_NEWS_ITEMS]]


def _to_dict(i: NewsItem) -> dict:
    return {
        "headline": i.headline,
        "description": i.description,
        "url": i.url,
        "published": i.published,
        "age_hours": round(i.age_hours, 1),
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
