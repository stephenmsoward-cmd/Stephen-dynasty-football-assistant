"""Historical snapshot reader.

Reads every dated JSON file in history/<slug>/ and builds per-team time series
for dynasty and win-now total values. Powers the sparklines on the league
standings.

Each daily run appends a new snapshot, so series grow over time. With only a
day or two of data, sparklines will look like a dot or short line — that's
expected. The infrastructure is ready to fill in.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_snapshots(history_dir: Path) -> list[tuple[str, dict]]:
    """Return [(date_str, parsed_json), ...] sorted ascending by date."""
    out: list[tuple[str, dict]] = []
    if not history_dir.exists():
        return out
    for path in sorted(history_dir.glob("*.json")):
        date_str = path.stem
        try:
            with path.open() as f:
                out.append((date_str, json.load(f)))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def build_team_series(history_dir: Path) -> dict[int, dict[str, list[dict]]]:
    """Returns {roster_id: {'dynasty': [{date, value}, ...], 'winnow': [...]}}."""
    series: dict[int, dict[str, list[dict]]] = {}
    for date_str, snap in load_snapshots(history_dir):
        for t in snap.get("teams", []):
            rid = t["roster_id"]
            modes = t.get("modes") or {}
            for mode in ("dynasty", "winnow"):
                value = modes.get(mode, {}).get("total_value", 0)
                series.setdefault(rid, {"dynasty": [], "winnow": []})[mode].append({
                    "date": date_str,
                    "value": value,
                })
    return series


def sparkline_svg(values: list[int], width: int = 60, height: int = 18, stroke: str = "currentColor") -> str:
    """Render an inline SVG sparkline. Returns empty string if fewer than 2 points."""
    if not values or len(values) < 2:
        # Single point: render as a small dot so the column doesn't look empty.
        if len(values) == 1:
            cx = width / 2
            cy = height / 2
            return (
                f'<svg class="sparkline" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="1.5" fill="{stroke}"/>'
                f'</svg>'
            )
        return ""
    vmin = min(values)
    vmax = max(values)
    span = max(1, vmax - vmin)
    n = len(values)
    points = []
    for i, v in enumerate(values):
        x = (i / (n - 1)) * (width - 2) + 1
        y = height - 1 - ((v - vmin) / span) * (height - 2)
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    return (
        f'<svg class="sparkline" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f'<polyline points="{polyline}" fill="none" stroke="{stroke}" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )
