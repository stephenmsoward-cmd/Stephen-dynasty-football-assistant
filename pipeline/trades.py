"""Trade finder V2.

Generates 1-for-1, 2-for-1, 1-for-2, and 2-for-2 trade candidates between
my team and each opposing team. Picks and players are both treated as
tradeable assets.

A candidate is shown when EACH team improves on at least one dimension:
  - Optimal starting lineup value (skill players that slot in), OR
  - Total dynasty asset value (the trade-market currency, including picks).

This dual-criterion is what makes pick-for-player trades work: the team
receiving the pick gains asset value while the team receiving the player
gains lineup value. Both sides have a reason to say yes.

Tier classification (set per candidate):
  - "mutual"   — both lineups strictly improve (classic balanced swap)
  - "buy"      — you send pick(s), receive player(s); you gain win-now lineup
  - "sell"     — you receive pick(s), send player(s); you gain future asset
  - "package"  — multi-player (any 2-for-1 / 1-for-2 / 2-for-2)
  - "asymmetric" — falls through other categories (still passes filters)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Iterable

from data import Player
from lineup import optimal_lineup

ValueFn = Callable[[Player], int]

# Per-side FC value parity tolerance: |send_total - receive_total| / max.
# Used during candidate generation so we keep the pool reasonable.
DEFAULT_VALUE_TOLERANCE = 0.20

# Tighter tolerance for the "mutual" tier specifically. If both lineups
# improve but FantasyCalc values are lopsided, no real manager accepts
# the trade — those candidates fall through to "asymmetric" instead.
MUTUAL_VALUE_TOLERANCE = 0.08

# Mutual tier also requires lineup gains to be reasonably balanced.
# min(my_change, their_change) / max(...) must be >= this threshold.
# 0.5 means neither side's lineup gain can be more than 2x the other's.
MUTUAL_LINEUP_BALANCE = 0.5

# Minimum positive change to count as "improvement" on a dimension.
LINEUP_MIN_IMPROVEMENT = 50
ASSET_MIN_IMPROVEMENT = 200

# Pruning: when enumerating multi-player packages, cap the pool to the top
# N most-valuable assets per side to keep 2-for-2 tractable.
PACKAGE_POOL_TOP_N = 15

# Minimum dynasty value to consider an asset tradeable at all.
MIN_TRADEABLE_VALUE = 300


def _is_pick(p: Player) -> bool:
    return p.position == "PICK"


def _asset_total(assets: list[Player]) -> int:
    return sum(p.dynasty_value for p in assets)


@dataclass
class TradeCandidate:
    send: list[Player]
    receive: list[Player]
    # Lineup math under value_fn (currently dynasty).
    my_lineup_old: int
    my_lineup_new: int
    their_lineup_old: int
    their_lineup_new: int
    # Total dynasty asset value per side.
    my_asset_old: int
    my_asset_new: int
    their_asset_old: int
    their_asset_new: int
    structure: str = ""        # "1v1", "2v1", "1v2", "2v2"
    pick_flow: str = "none"    # "to_me", "to_them", "both", "none"
    tier: str = "asymmetric"   # mutual / buy / sell / package / asymmetric

    @property
    def my_lineup_change(self) -> int:
        return self.my_lineup_new - self.my_lineup_old

    @property
    def their_lineup_change(self) -> int:
        return self.their_lineup_new - self.their_lineup_old

    @property
    def my_asset_change(self) -> int:
        return self.my_asset_new - self.my_asset_old

    @property
    def their_asset_change(self) -> int:
        return self.their_asset_new - self.their_asset_old

    @property
    def my_value_delta(self) -> int:
        """Positive = I gain FC dynasty value across the trade."""
        return _asset_total(self.receive) - _asset_total(self.send)

    @property
    def score(self) -> int:
        """Sum of positive improvements across both sides, both dimensions."""
        return (
            max(0, self.my_lineup_change)
            + max(0, self.my_asset_change)
            + max(0, self.their_lineup_change)
            + max(0, self.their_asset_change)
        )


def _classify(c: TradeCandidate) -> str:
    """Categorize the trade for UI tiering."""
    my_l_up = c.my_lineup_change >= LINEUP_MIN_IMPROVEMENT
    their_l_up = c.their_lineup_change >= LINEUP_MIN_IMPROVEMENT

    # "Mutual" must satisfy THREE conditions:
    # 1. Both lineups improve (algorithmic fit)
    # 2. FantasyCalc value parity is tight (market plausibility)
    # 3. Lineup gains are reasonably balanced (neither side dwarfs the other)
    # Without (2) one side takes a worse market deal; without (3) one side
    # barely benefits while the other gets the bulk of the lineup upgrade.
    if my_l_up and their_l_up:
        send_total = _asset_total(c.send)
        receive_total = _asset_total(c.receive)
        larger = max(send_total, receive_total)
        value_ok = larger > 0 and abs(send_total - receive_total) / larger <= MUTUAL_VALUE_TOLERANCE

        max_lineup = max(c.my_lineup_change, c.their_lineup_change)
        balance_ok = max_lineup > 0 and (min(c.my_lineup_change, c.their_lineup_change) / max_lineup) >= MUTUAL_LINEUP_BALANCE

        if value_ok and balance_ok:
            return "mutual"
        # Falls through to other tiers below.

    sending_pick = any(_is_pick(p) for p in c.send)
    receiving_pick = any(_is_pick(p) for p in c.receive)

    if sending_pick and not receiving_pick and my_l_up:
        return "buy"   # I send picks, I gain win-now value
    if receiving_pick and not sending_pick and their_l_up:
        return "sell"  # I get picks, they gain win-now value (and I gain asset)

    if len(c.send) > 1 or len(c.receive) > 1:
        return "package"

    return "asymmetric"


def _set_pick_flow(c: TradeCandidate) -> str:
    sending_pick = any(_is_pick(p) for p in c.send)
    receiving_pick = any(_is_pick(p) for p in c.receive)
    if sending_pick and receiving_pick:
        return "both"
    if sending_pick:
        return "to_them"
    if receiving_pick:
        return "to_me"
    return "none"


def _structure(send: list[Player], receive: list[Player]) -> str:
    return f"{len(send)}v{len(receive)}"


def _meets_value_parity(send: list[Player], receive: list[Player], tolerance: float) -> bool:
    s = _asset_total(send)
    r = _asset_total(receive)
    larger = max(s, r)
    if larger == 0:
        return False
    return abs(s - r) / larger <= tolerance


def _passes_improvement(
    my_lineup_change: int,
    my_asset_change: int,
    their_lineup_change: int,
    their_asset_change: int,
) -> bool:
    """Each side must improve on EITHER lineup or asset value."""
    me_ok = (
        my_lineup_change >= LINEUP_MIN_IMPROVEMENT
        or my_asset_change >= ASSET_MIN_IMPROVEMENT
    )
    them_ok = (
        their_lineup_change >= LINEUP_MIN_IMPROVEMENT
        or their_asset_change >= ASSET_MIN_IMPROVEMENT
    )
    return me_ok and them_ok


def _enumerate_packages(pool: list[Player], max_size: int) -> Iterable[tuple[Player, ...]]:
    """Yield 1-tuples, 2-tuples, ... up to max_size from pool."""
    for size in range(1, max_size + 1):
        for combo in combinations(pool, size):
            yield combo


def find_trades(
    my_tradeable: list[Player],
    my_players: list[Player],           # lineup pool (no picks)
    their_tradeable: list[Player],
    their_players: list[Player],
    slots: list[str],
    value_fn: ValueFn,
    value_tolerance: float = DEFAULT_VALUE_TOLERANCE,
    max_side_size: int = 2,
) -> list[TradeCandidate]:
    """Brute-force enumeration of 1-for-1, 2-for-1, 1-for-2, 2-for-2.
    Heavy pre-filtering on value parity to keep lineup recomputes manageable."""

    # Baselines.
    my_baseline_lineup = optimal_lineup(my_players, slots, value_fn=value_fn).total_value
    their_baseline_lineup = optimal_lineup(their_players, slots, value_fn=value_fn).total_value
    my_baseline_asset = _asset_total(my_tradeable)
    their_baseline_asset = _asset_total(their_tradeable)

    # Filter tradeables by minimum value.
    my_valued = [p for p in my_tradeable if p.dynasty_value >= MIN_TRADEABLE_VALUE]
    their_valued = [p for p in their_tradeable if p.dynasty_value >= MIN_TRADEABLE_VALUE]

    # Pruned pools for multi-player enumeration (top N by dynasty value).
    my_top = sorted(my_valued, key=lambda p: p.dynasty_value, reverse=True)[:PACKAGE_POOL_TOP_N]
    their_top = sorted(their_valued, key=lambda p: p.dynasty_value, reverse=True)[:PACKAGE_POOL_TOP_N]

    candidates: list[TradeCandidate] = []
    seen_pairs: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()

    def consider(send: tuple[Player, ...], receive: tuple[Player, ...]) -> None:
        if not _meets_value_parity(list(send), list(receive), value_tolerance):
            return

        send_ids = tuple(sorted(p.sleeper_id for p in send))
        receive_ids = tuple(sorted(p.sleeper_id for p in receive))
        if (send_ids, receive_ids) in seen_pairs:
            return
        seen_pairs.add((send_ids, receive_ids))

        # Lineup recompute uses only skill players (picks can't slot anyway).
        send_set = set(send_ids)
        receive_set = set(receive_ids)
        new_my_players = [p for p in my_players if p.sleeper_id not in send_set] + [
            p for p in receive if not _is_pick(p)
        ]
        new_their_players = [p for p in their_players if p.sleeper_id not in receive_set] + [
            p for p in send if not _is_pick(p)
        ]

        new_my_lineup = optimal_lineup(new_my_players, slots, value_fn=value_fn).total_value
        new_their_lineup = optimal_lineup(new_their_players, slots, value_fn=value_fn).total_value

        # Asset value: zero-sum on dynasty market. Sum stays balanced.
        my_val_delta = _asset_total(list(receive)) - _asset_total(list(send))
        new_my_asset = my_baseline_asset + my_val_delta
        new_their_asset = their_baseline_asset - my_val_delta

        my_lineup_change = new_my_lineup - my_baseline_lineup
        their_lineup_change = new_their_lineup - their_baseline_lineup

        if not _passes_improvement(
            my_lineup_change, my_val_delta,
            their_lineup_change, -my_val_delta,
        ):
            return

        c = TradeCandidate(
            send=list(send),
            receive=list(receive),
            my_lineup_old=my_baseline_lineup,
            my_lineup_new=new_my_lineup,
            their_lineup_old=their_baseline_lineup,
            their_lineup_new=new_their_lineup,
            my_asset_old=my_baseline_asset,
            my_asset_new=new_my_asset,
            their_asset_old=their_baseline_asset,
            their_asset_new=new_their_asset,
            structure=_structure(list(send), list(receive)),
        )
        c.pick_flow = _set_pick_flow(c)
        c.tier = _classify(c)
        candidates.append(c)

    # 1-for-1: full pool both sides.
    for s in my_valued:
        for r in their_valued:
            consider((s,), (r,))

    # 2-for-1: my pairs × their singles (pruned pool for pairs).
    for s_pair in combinations(my_top, 2):
        for r in their_valued:
            consider(s_pair, (r,))

    # 1-for-2: my singles × their pairs.
    for s in my_valued:
        for r_pair in combinations(their_top, 2):
            consider((s,), r_pair)

    # 2-for-2 (smallest pool both sides — keeps it tractable).
    for s_pair in combinations(my_top, 2):
        for r_pair in combinations(their_top, 2):
            consider(s_pair, r_pair)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
