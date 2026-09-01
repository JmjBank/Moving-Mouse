"""Configuration validation tests (cross-platform)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config_loader import load_config, validate_config
from app.exceptions import ConfigurationError


class ConfigValidationTests(unittest.TestCase):
    def test_default_config_is_valid(self) -> None:
        config = load_config(Path("config.yaml"))
        validate_config(config)
        self.assertEqual(config["timing"]["interval_seconds"], 180)
        self.assertEqual(config["teams_click"]["clicks"], 1)

    def test_invalid_interval(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(
                "timing:\n  interval_seconds: 0\n"
                "windows:\n  youtube:\n    title_keywords: [YouTube]\n"
                "  teams:\n    title_keywords: [Teams]\n"
                "teams_click:\n  x: 1\n  y: 1\n  clicks: 1\n"
            )
            path = Path(handle.name)

        try:
            config = load_config(path)
            with self.assertRaises(ConfigurationError) as ctx:
                validate_config(config)
            self.assertIn("interval_seconds", str(ctx.exception))
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_clicks(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(
                "timing:\n  interval_seconds: 60\n"
                "windows:\n  youtube:\n    title_keywords: [YouTube]\n"
                "  teams:\n    title_keywords: [Teams]\n"
                "teams_click:\n  x: 1\n  y: 1\n  clicks: 2\n"
            )
            path = Path(handle.name)

        try:
            config = load_config(path)
            with self.assertRaises(ConfigurationError) as ctx:
                validate_config(config)
            self.assertIn("clicks", str(ctx.exception))
        finally:
            path.unlink(missing_ok=True)

    def test_empty_youtube_keywords(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(
                "timing:\n  interval_seconds: 60\n"
                "windows:\n  youtube:\n    title_keywords: []\n"
                "  teams:\n    title_keywords: [Teams]\n"
                "teams_click:\n  x: 1\n  y: 1\n  clicks: 1\n"
            )
            path = Path(handle.name)

        try:
            config = load_config(path)
            with self.assertRaises(ConfigurationError) as ctx:
                validate_config(config)
            self.assertIn("youtube.title_keywords", str(ctx.exception))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
