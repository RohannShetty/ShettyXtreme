"""Voter correlation detection and block-cap application.

Detects groups of voters whose direction agrees too often (redundant signal)
and applies a block cap so a correlated group cannot dominate conviction.
Stdlib only — no scipy/pandas.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

from shettyxtreme.intelligence.signals.signal_engine import Vote


class VoterCorrelation:
    """Compute voter agreement and apply correlated-group block caps."""

    def __init__(self, block_cap: float = 2.0) -> None:
        self._block_cap: float = block_cap
        self._correlation_matrix: dict[tuple[str, str], float] = {}

    def compute_correlation_matrix(
        self, votes: list[list[Vote]]
    ) -> dict[tuple[str, str], float]:
        """Return {(name_a, name_b): agreement 0..1} over co-occurring signals."""
        pair_stats: dict[tuple[str, str], list[int]] = {}
        for signal_votes in votes:
            for a, b in combinations(signal_votes, 2):
                key = (a.name, b.name)
                stats = pair_stats.setdefault(key, [0, 0])
                stats[1] += 1
                if self._same_sign(a.direction, b.direction):
                    stats[0] += 1
        matrix: dict[tuple[str, str], float] = {}
        for key, (agree, total) in pair_stats.items():
            matrix[key] = agree / total if total > 0 else 0.0
        self._correlation_matrix = matrix
        return matrix

    def get_correlation_groups(
        self, threshold: float = 0.7
    ) -> list[list[str]]:
        """Union-find connected components of voters with agreement > threshold."""
        names: set[str] = set()
        for a, b in self._correlation_matrix:
            names.add(a)
            names.add(b)
        parent: dict[str, str] = {n: n for n in names}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: str, y: str) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        for (a, b), val in self._correlation_matrix.items():
            if val > threshold:
                union(a, b)

        groups_map: dict[str, list[str]] = {}
        for n in names:
            root = find(n)
            groups_map.setdefault(root, []).append(n)
        return list(groups_map.values())

    def get_block_cap(self, group: list[str]) -> float:
        """Return the configured max total weight for a correlated group."""
        return self._block_cap

    def apply_block_caps(
        self, votes: list[Vote], caps: dict[str, float]
    ) -> list[Vote]:
        """Scale weights of capped groups so group total == cap.

        caps maps voter NAME -> max allowed total weight for the group that
        name belongs to. Returns a NEW list of Votes (inputs not mutated).
        """
        new_votes: list[Vote] = []
        by_cap: dict[float, list[Vote]] = {}
        for v in votes:
            cap = caps.get(v.name)
            if cap is None:
                new_votes.append(
                    Vote(
                        direction=v.direction,
                        confidence=v.confidence,
                        weight=v.weight,
                        name=v.name,
                    )
                )
            else:
                by_cap.setdefault(cap, []).append(v)

        for cap, group in by_cap.items():
            total = sum(v.weight for v in group)
            if total > cap and total > 0:
                scale = cap / total
                for v in group:
                    new_votes.append(
                        Vote(
                            direction=v.direction,
                            confidence=v.confidence,
                            weight=v.weight * scale,
                            name=v.name,
                        )
                    )
            else:
                for v in group:
                    new_votes.append(
                        Vote(
                            direction=v.direction,
                            confidence=v.confidence,
                            weight=v.weight,
                            name=v.name,
                        )
                    )
        return new_votes

    @staticmethod
    def _same_sign(x: float, y: float) -> bool:
        if x > 0 and y > 0:
            return True
        if x < 0 and y < 0:
            return True
        if x == 0 and y == 0:
            return True
        return False
