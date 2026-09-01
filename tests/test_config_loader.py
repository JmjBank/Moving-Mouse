"""Configuration validation tests (cross-platform)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config_loader import load_config, validate_config
from app.exceptions import ConfigurationError

BASE_CONFIG = """
activity_monitor:
  enabled: true
  idle_threshold_seconds: 180
  poll_interval_seconds: 1
timing:
  teams_activation_delay_seconds: 2
  after_click_delay_seconds: 1
windows:
  youtube:
    title_keywords: [YouTube]
  teams:
    title_keywords: [Teams]
teams_click:
  x: 1
  y: 1
  clicks: 1
"""


class ConfigValidationTests(unittest.TestCase):
    def test_default_config_is_valid(self) -> None:
        config = load_config(Path("config.yaml"))
        validate_config(config)
        self.assertEqual(config["activity_monitor"]["idle_threshold_seconds"], 180)
        self.assertEqual(config["teams_click"]["clicks"], 1)

    def test_invalid_idle_threshold(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(
                BASE_CONFIG.replace("idle_threshold_seconds: 180", "idle_threshold_seconds: 0")
            )
            path = Path(handle.name)

        try:
            config = load_config(path)
            with self.assertRaises(ConfigurationError) as ctx:
                validate_config(config)
            self.assertIn("idle_threshold_seconds", str(ctx.exception))
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_poll_interval(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(
                BASE_CONFIG.replace("poll_interval_seconds: 1", "poll_interval_seconds: 180")
            )
            path = Path(handle.name)

        try:
            config = load_config(path)
            with self.assertRaises(ConfigurationError) as ctx:
                validate_config(config)
            self.assertIn("poll_interval_seconds", str(ctx.exception))
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_clicks(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(BASE_CONFIG.replace("clicks: 1", "clicks: 2"))
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
                BASE_CONFIG.replace(
                    "title_keywords: [YouTube]",
                    "title_keywords: []",
                    1,
                )
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
