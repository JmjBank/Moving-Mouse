"""Pure helpers for choosing the best window title match."""

from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def score_title_for_keywords(title: str, keywords: Sequence[str]) -> int:
    """Return the length of the longest keyword contained in ``title``."""
    title_lower = title.lower()
    best = 0
    for keyword in keywords:
        normalized = keyword.lower()
        if normalized and normalized in title_lower:
            best = max(best, len(normalized))
    return best


def choose_best_scored_item(
    items: Sequence[tuple[int, T]],
) -> T | None:
    """Pick the item with the highest score; stable on ties (first wins)."""
    if not items:
        return None

    best_score = max(score for score, _ in items)
    for score, item in items:
        if score == best_score:
            return item
    return None
