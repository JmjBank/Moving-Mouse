"""Windows process name matching helpers (cross-platform)."""

from __future__ import annotations

import unittest

from app.window_process import executable_matches_process_names


class ExecutableMatchTests(unittest.TestCase):
    def test_matches_basename(self) -> None:
        self.assertTrue(
            executable_matches_process_names("ms-teams.exe", ["ms-teams.exe"])
        )

    def test_matches_full_path(self) -> None:
        self.assertTrue(
            executable_matches_process_names(
                r"C:\Program Files\Microsoft Teams\ms-teams.exe",
                ["ms-teams.exe"],
            )
        )

    def test_no_match(self) -> None:
        self.assertFalse(
            executable_matches_process_names("chrome.exe", ["ms-teams.exe"])
        )


if __name__ == "__main__":
    unittest.main()
