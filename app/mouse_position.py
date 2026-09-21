"""Helpers for choosing safe cursor coordinates within a window."""

from __future__ import annotations

import random
from typing import Sequence


def random_point_in_rectangle(
    rect: Sequence[int],
    margin_pixels: int,
    *,
    rng: random.Random | None = None,
) -> tuple[int, int] | None:
    """
    Pick a random screen coordinate inside ``rect`` with ``margin_pixels`` inset.

    ``rect`` is ``(left, top, right, bottom)`` in screen coordinates as returned by
    ``GetWindowRect``. Returns ``None`` when the inset region is too small.
    """
    if len(rect) != 4:
        raise ValueError("rect must contain exactly four integers")

    left, top, right, bottom = (int(value) for value in rect)
    margin = max(0, int(margin_pixels))

    inner_left = left + margin
    inner_top = top + margin
    inner_right = right - margin
    inner_bottom = bottom - margin

    if inner_left >= inner_right or inner_top >= inner_bottom:
        return None

    randomizer = rng if rng is not None else random.Random()
    max_x = inner_right - 1
    max_y = inner_bottom - 1
    x = randomizer.randint(inner_left, max_x)
    y = randomizer.randint(inner_top, max_y)
    return x, y


def center_point_in_rectangle(
    rect: Sequence[int],
    *,
    vertical_ratio: float = 0.58,
) -> tuple[int, int]:
    """
    Return a point near the visual center of a browser window.

    ``vertical_ratio`` shifts below the geometric center to avoid the tab/toolbar
    area (0.5 = dead center, ~0.58 ≈ typical video region in Chrome/Edge).
    """
    if len(rect) != 4:
        raise ValueError("rect must contain exactly four integers")

    left, top, right, bottom = (int(value) for value in rect)
    ratio = min(max(float(vertical_ratio), 0.0), 1.0)
    x = left + (right - left) // 2
    y = top + int((bottom - top) * ratio)
    return x, y
