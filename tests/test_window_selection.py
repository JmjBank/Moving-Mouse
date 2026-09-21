"""Window title scoring helpers (cross-platform)."""

from __future__ import annotations

import unittest

from app.window_selection import choose_best_scored_item, score_title_for_keywords


class WindowSelectionTests(unittest.TestCase):
    def test_prefers_longer_keyword_match(self) -> None:
        score = score_title_for_keywords(
            "Chat | Microsoft Teams",
            ["Microsoft Teams", "Teams"],
        )
        self.assertEqual(score, len("microsoft teams"))

    def test_choose_best_scored_item_returns_highest_score(self) -> None:
        chosen = choose_best_scored_item(
            [
                (5, "short-match"),
                (14, "microsoft-teams-match"),
            ]
        )
        self.assertEqual(chosen, "microsoft-teams-match")


if __name__ == "__main__":
    unittest.main()
