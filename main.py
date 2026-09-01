#!/usr/bin/env python3
"""YouTube ↔ Microsoft Teams continuous automation entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config.yaml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor Windows user idle time and automate switching between an existing "
            "YouTube browser window and Microsoft Teams, performing one safe click in "
            "Teams after each idle threshold is reached."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML or JSON configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--show-mouse-position",
        action="store_true",
        help="Print the current mouse coordinates and exit (helper for teams_click config)",
    )
    return parser.parse_args()


def get_mouse_position() -> tuple[int, int]:
    """Return current cursor coordinates using the best available platform API."""
    if sys.platform == "win32":
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            raise OSError("GetCursorPos failed")
        return point.x, point.y

    if sys.platform.startswith("linux"):
        from Xlib import display

        pointer = display.Display().screen().root.query_pointer()._data
        return int(pointer["root_x"]), int(pointer["root_y"])

    import pyautogui

    position = pyautogui.position()
    return int(position.x), int(position.y)


def show_mouse_position() -> int:
    try:
        x, y = get_mouse_position()
    except Exception as exc:
        print(f"ERROR: Could not read mouse position: {exc}", file=sys.stderr)
        return 1

    print(f"Current mouse position: X={x} Y={y}")
    return 0


def run_application(config_path: Path) -> int:
    from app.automation import AutomationEngine
    from app.config_loader import load_config, validate_config
    from app.exceptions import ConfigurationError, PlatformNotSupportedError
    from app.idle_monitor import IdleMonitor
    from app.logger import setup_logging
    from app.window_manager import WindowManager

    try:
        config = load_config(config_path)
        validate_config(config)
    except ConfigurationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    logger = setup_logging(config)
    logger.info("Application started")
    logger.info("Configuration loaded: %s", config_path)

    if not config["application"].get("enabled", True):
        logger.info("Application is disabled in configuration (application.enabled=false).")
        logger.info("Application stopped.")
        return 0

    if not config["activity_monitor"].get("enabled", True):
        logger.info(
            "Activity monitor is disabled in configuration (activity_monitor.enabled=false)."
        )
        logger.info("Application stopped.")
        return 0

    try:
        window_manager = WindowManager(config)
        idle_monitor = IdleMonitor()
    except PlatformNotSupportedError as exc:
        logger.error(str(exc))
        return 1

    engine = AutomationEngine(config, window_manager)

    try:
        engine.run_idle_monitoring(idle_monitor)
    except KeyboardInterrupt:
        logger.info("Stop requested by user.")
        logger.info("Application shutting down gracefully.")
        logger.info("Application stopped.")
        return 0

    return 0


def main() -> int:
    args = parse_args()

    if args.show_mouse_position:
        return show_mouse_position()

    return run_application(Path(args.config))


if __name__ == "__main__":
    sys.exit(main())
