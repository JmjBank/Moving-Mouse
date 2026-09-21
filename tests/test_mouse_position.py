"""Random YouTube cursor placement helpers (cross-platform)."""

from __future__ import annotations

import random
import unittest

from app.mouse_position import center_point_in_rectangle, random_point_in_rectangle


class RandomPointInRectangleTests(unittest.TestCase):
    def test_point_stays_inside_margin(self) -> None:
        rng = random.Random(0)
        rect = (100, 200, 500, 600)
        margin = 50

        for _ in range(20):
            point = random_point_in_rectangle(rect, margin, rng=rng)
            self.assertIsNotNone(point)
            x, y = point
            self.assertGreaterEqual(x, 150)
            self.assertLessEqual(x, 449)
            self.assertGreaterEqual(y, 250)
            self.assertLessEqual(y, 549)

    def test_returns_none_when_window_too_small(self) -> None:
        rect = (0, 0, 100, 100)
        self.assertIsNone(random_point_in_rectangle(rect, 80))

    def test_center_point_uses_vertical_ratio(self) -> None:
        x, y = center_point_in_rectangle((0, 0, 100, 100), vertical_ratio=0.58)
        self.assertEqual(x, 50)
        self.assertEqual(y, 57)

    def test_zero_margin_uses_full_rect(self) -> None:
        rng = random.Random(1)
        point = random_point_in_rectangle((10, 10, 20, 20), 0, rng=rng)
        self.assertIsNotNone(point)
        x, y = point
        self.assertGreaterEqual(x, 10)
        self.assertLessEqual(x, 19)
        self.assertGreaterEqual(y, 10)
        self.assertLessEqual(y, 19)


if __name__ == "__main__":
    unittest.main()
