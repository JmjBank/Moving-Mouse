"""Automation cycle execution and continuous application loop."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.exceptions import RecoverableAutomationError
from app.window_manager import WindowManager

logger = logging.getLogger("youtube_teams_automation")


class AutomationEngine:
    """Runs one automation cycle and the continuous outer loop."""

    def __init__(self, config: dict[str, Any], window_manager: WindowManager) -> None:
        self._config = config
        self._window_manager = window_manager
        self._cycle_count = 0

    @property
    def interval_seconds(self) -> float:
        return float(self._config["timing"]["interval_seconds"])

    def run_continuous(self) -> None:
        """Run automation cycles until interrupted by the user."""
        timing = self._config["timing"]
        startup_delay = float(timing.get("startup_delay_seconds", 0))

        if startup_delay > 0:
            logger.info("Startup delay: %.0f seconds", startup_delay)
            self._interruptible_sleep(startup_delay)

        logger.info("Continuous automation mode enabled")

        while True:
            self._wait_for_next_cycle()
            self._cycle_count += 1

            try:
                self.execute_cycle(self._cycle_count)
            except RecoverableAutomationError as exc:
                logger.error("Automation cycle failed: %s", exc)
                logger.info("Application remains active.")

            logger.info(
                "Next automation cycle in %.0f seconds",
                self.interval_seconds,
            )

    def execute_cycle(self, cycle_number: int) -> None:
        """Execute a single YouTube → Teams → click → YouTube cycle."""
        logger.info("Automation cycle #%s started", cycle_number)

        teams_keywords = self._config["windows"]["teams"]["title_keywords"]
        youtube_keywords = self._config["windows"]["youtube"]["title_keywords"]
        timing = self._config["timing"]
        teams_click = self._config["teams_click"]

        teams_window = self._window_manager.find_window_by_keywords(teams_keywords)
        if teams_window is None:
            logger.warning("Microsoft Teams window not found. Click action skipped.")
            logger.info("Application remains active.")
            return

        logger.info("Microsoft Teams window found: '%s'", teams_window.title)
        logger.info("Switching to Microsoft Teams")

        if not self._window_manager.activate_window(teams_window):
            logger.error(
                "Microsoft Teams could not be activated. Click cancelled for safety."
            )
            self._switch_back_to_youtube(youtube_keywords)
            return

        activation_delay = float(timing["teams_activation_delay_seconds"])
        if activation_delay > 0:
            self._interruptible_sleep(activation_delay)

        if not self._window_manager.is_foreground_window(teams_window):
            foreground_title = self._window_manager.get_foreground_title()
            logger.error(
                "Microsoft Teams is not the foreground window. Click cancelled. "
                "Current foreground: '%s'",
                foreground_title,
            )
            self._switch_back_to_youtube(youtube_keywords)
            return

        logger.info("Microsoft Teams verified as foreground")

        click_x = int(teams_click["x"])
        click_y = int(teams_click["y"])
        button = str(teams_click.get("button", "left"))

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0
            pyautogui.click(
                x=click_x,
                y=click_y,
                clicks=1,
                button=button,
            )
            logger.info("Mouse click executed at x=%s, y=%s", click_x, click_y)
        except Exception as exc:
            raise RecoverableAutomationError(f"Mouse click failed: {exc}") from exc

        after_click_delay = float(timing["after_click_delay_seconds"])
        if after_click_delay > 0:
            self._interruptible_sleep(after_click_delay)

        self._switch_back_to_youtube(youtube_keywords)
        logger.info("Automation cycle #%s completed", cycle_number)

    def _switch_back_to_youtube(self, youtube_keywords: list[str]) -> None:
        """Activate the existing YouTube window when available."""
        youtube_window = self._window_manager.find_window_by_keywords(youtube_keywords)
        if youtube_window is None:
            logger.warning("YouTube window not found. Current cycle skipped.")
            return

        logger.info("Switching back to YouTube: '%s'", youtube_window.title)
        if not self._window_manager.activate_window(youtube_window):
            logger.warning("YouTube window could not be activated.")

    def _wait_for_next_cycle(self) -> None:
        logger.info("Next automation cycle in %.0f seconds", self.interval_seconds)
        self._interruptible_sleep(self.interval_seconds)

    @staticmethod
    def _interruptible_sleep(seconds: float) -> None:
        """Sleep in short chunks so CTRL+C is handled promptly at the outer level."""
        if seconds <= 0:
            return

        end_time = time.monotonic() + seconds
        while True:
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.5, remaining))
