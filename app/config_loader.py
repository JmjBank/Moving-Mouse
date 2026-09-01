"""Load and validate external application configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from app.exceptions import ConfigurationError

DEFAULT_CONFIG: dict[str, Any] = {
    "application": {
        "name": "YouTube Teams Auto Switch",
        "enabled": True,
    },
    "timing": {
        "teams_activation_delay_seconds": 2,
        "after_click_delay_seconds": 1,
        "startup_delay_seconds": 3,
    },
    "activity_monitor": {
        "enabled": True,
        "idle_threshold_seconds": 180,
        "poll_interval_seconds": 1,
    },
    "windows": {
        "youtube": {
            "title_keywords": ["YouTube"],
        },
        "teams": {
            "title_keywords": ["Microsoft Teams", "Teams"],
        },
    },
    "teams_click": {
        "x": 850,
        "y": 620,
        "button": "left",
        "clicks": 1,
    },
    "logging": {
        "level": "INFO",
        "log_to_console": True,
        "log_to_file": True,
        "file": "logs/app.log",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load YAML or JSON configuration and merge with safe defaults."""
    path = Path(config_path)
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(raw_text)
    elif suffix == ".json":
        loaded = json.loads(raw_text)
    else:
        raise ConfigurationError(
            f"Unsupported configuration format: {path.suffix}. Use .yaml, .yml, or .json"
        )

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ConfigurationError("Configuration root must be a mapping/object")

    return _deep_merge(DEFAULT_CONFIG, loaded)


def validate_config(config: dict[str, Any]) -> None:
    """Validate configuration values. Raises ConfigurationError on failure."""
    application = config.get("application")
    if not isinstance(application, dict):
        raise ConfigurationError("Invalid configuration: application must be an object")

    enabled = application.get("enabled")
    if not isinstance(enabled, bool):
        raise ConfigurationError(
            "Invalid configuration: application.enabled must be a boolean"
        )

    timing = config.get("timing")
    if not isinstance(timing, dict):
        raise ConfigurationError("Invalid configuration: timing must be an object")

    for field in (
        "teams_activation_delay_seconds",
        "after_click_delay_seconds",
        "startup_delay_seconds",
    ):
        value = timing.get(field)
        if not isinstance(value, (int, float)) or value < 0:
            raise ConfigurationError(
                f"Invalid configuration: timing.{field} must be greater than or equal to 0"
            )

    activity_monitor = config.get("activity_monitor")
    if not isinstance(activity_monitor, dict):
        raise ConfigurationError(
            "Invalid configuration: activity_monitor must be an object"
        )

    monitor_enabled = activity_monitor.get("enabled")
    if not isinstance(monitor_enabled, bool):
        raise ConfigurationError(
            "Invalid configuration: activity_monitor.enabled must be a boolean"
        )

    idle_threshold_seconds = activity_monitor.get("idle_threshold_seconds")
    if not isinstance(idle_threshold_seconds, (int, float)) or idle_threshold_seconds <= 0:
        raise ConfigurationError(
            "Invalid configuration: activity_monitor.idle_threshold_seconds must be greater than 0"
        )

    poll_interval_seconds = activity_monitor.get("poll_interval_seconds")
    if not isinstance(poll_interval_seconds, (int, float)) or poll_interval_seconds <= 0:
        raise ConfigurationError(
            "Invalid configuration: activity_monitor.poll_interval_seconds must be greater than 0"
        )

    if poll_interval_seconds >= idle_threshold_seconds:
        raise ConfigurationError(
            "Invalid configuration: activity_monitor.poll_interval_seconds must be less than activity_monitor.idle_threshold_seconds"
        )

    windows = config.get("windows")
    if not isinstance(windows, dict):
        raise ConfigurationError("Invalid configuration: windows must be an object")

    youtube = windows.get("youtube")
    if not isinstance(youtube, dict):
        raise ConfigurationError(
            "Invalid configuration: windows.youtube must be an object"
        )
    youtube_keywords = youtube.get("title_keywords")
    if not isinstance(youtube_keywords, list) or not youtube_keywords:
        raise ConfigurationError(
            "Invalid configuration: windows.youtube.title_keywords must not be empty"
        )

    teams = windows.get("teams")
    if not isinstance(teams, dict):
        raise ConfigurationError("Invalid configuration: windows.teams must be an object")
    teams_keywords = teams.get("title_keywords")
    if not isinstance(teams_keywords, list) or not teams_keywords:
        raise ConfigurationError(
            "Invalid configuration: windows.teams.title_keywords must not be empty"
        )

    teams_click = config.get("teams_click")
    if not isinstance(teams_click, dict):
        raise ConfigurationError("Invalid configuration: teams_click must be an object")

    x_coord = teams_click.get("x")
    y_coord = teams_click.get("y")
    if not isinstance(x_coord, (int, float)) or x_coord < 0:
        raise ConfigurationError("Invalid configuration: teams_click.x must be >= 0")
    if not isinstance(y_coord, (int, float)) or y_coord < 0:
        raise ConfigurationError("Invalid configuration: teams_click.y must be >= 0")

    clicks = teams_click.get("clicks")
    if clicks != 1:
        raise ConfigurationError("Invalid configuration: teams_click.clicks must equal 1")

    button = teams_click.get("button", "left")
    if button not in {"left", "right", "middle"}:
        raise ConfigurationError(
            "Invalid configuration: teams_click.button must be left, right, or middle"
        )
