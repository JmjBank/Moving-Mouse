"""Automation cycle execution and idle-triggered monitoring loop."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

from app.exceptions import IdleDetectionError, RecoverableAutomationError
from app.idle_monitor import IdleAutomationState, IdleMonitor
from app.mouse_position import random_point_in_rectangle
from app.window_manager import WindowInfo, WindowManager

logger = logging.getLogger("youtube_teams_automation")


class CycleResult(Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AutomationEngine:
    """Runs idle monitoring and single automation cycles."""

    def __init__(self, config: dict[str, Any], window_manager: WindowManager) -> None:
        self._config = config
        self._window_manager = window_manager
        self._cycle_count = 0

    def run_idle_monitoring(self, idle_monitor: IdleMonitor) -> None:
        """Monitor user idle time and trigger automation cycles until interrupted."""
        activity_config = self._config["activity_monitor"]
        timing = self._config["timing"]
        threshold_seconds = float(activity_config["idle_threshold_seconds"])
        poll_interval = float(activity_config["poll_interval_seconds"])
        startup_delay = float(timing.get("startup_delay_seconds", 0))

        if startup_delay > 0:
            logger.info("Startup delay: %.0f seconds", startup_delay)
            self._interruptible_sleep(startup_delay)

        state = IdleAutomationState()

        try:
            initial_tick = idle_monitor.get_last_input_tick()
        except IdleDetectionError as exc:
            raise RecoverableAutomationError(
                f"Unable to initialize idle monitoring: {exc}"
            ) from exc

        state.initialize(initial_tick)

        logger.info("User idle monitoring enabled")
        logger.info("Idle threshold: %.0f seconds", threshold_seconds)
        logger.info("Continuous automation mode enabled")

        while True:
            try:
                idle_seconds = idle_monitor.get_idle_seconds()
                current_input_tick = idle_monitor.get_last_input_tick()
            except IdleDetectionError:
                logger.error("Unable to determine Windows user idle time.")
                self._interruptible_sleep(poll_interval)
                continue

            logger.debug("User idle: %.1f seconds", idle_seconds)

            state.poll_for_activity_reset(current_input_tick)

            if state.should_trigger_automation(idle_seconds, threshold_seconds):
                logger.info("User idle threshold reached")
                state.on_automation_started(current_input_tick)
                self._cycle_count += 1

                try:
                    result = self.execute_cycle(
                        self._cycle_count,
                        idle_monitor=idle_monitor,
                        idle_state=state,
                    )
                except RecoverableAutomationError as exc:
                    logger.error("Automation cycle failed: %s", exc)
                    logger.info("Application remains active.")
                    try:
                        post_tick = idle_monitor.get_last_input_tick()
                    except IdleDetectionError:
                        state.on_automation_cancelled()
                    else:
                        state.on_automation_skipped(post_tick)
                        logger.info("Current idle period marked as processed")
                    self._interruptible_sleep(poll_interval)
                    continue

                if result == CycleResult.CANCELLED:
                    state.on_automation_cancelled()
                elif result in {CycleResult.COMPLETED, CycleResult.SKIPPED}:
                    try:
                        post_tick = idle_monitor.get_last_input_tick()
                    except IdleDetectionError:
                        state.on_automation_cancelled()
                    else:
                        state.on_automation_skipped(post_tick)
                        logger.info("Current idle period marked as processed")

            self._interruptible_sleep(poll_interval)

    def execute_cycle(
        self,
        cycle_number: int,
        *,
        idle_monitor: IdleMonitor | None = None,
        idle_state: IdleAutomationState | None = None,
    ) -> CycleResult:
        """Execute a single YouTube → Teams → click → YouTube cycle."""
        logger.info("Automation cycle #%s started", cycle_number)

        teams_config = self._config["windows"]["teams"]
        youtube_keywords = self._config["windows"]["youtube"]["title_keywords"]
        timing = self._config["timing"]
        teams_click = self._config["teams_click"]

        youtube_window = self._window_manager.resolve_youtube_window(youtube_keywords)
        if youtube_window is None:
            logger.warning(
                "YouTube window not found before automation cycle. "
                "Restore after Teams may fail; check windows.youtube.title_keywords."
            )

        exclude_youtube_handle = (
            youtube_window.handle if youtube_window is not None else None
        )
        teams_window = self._window_manager.resolve_teams_window(
            teams_config,
            exclude_handle=exclude_youtube_handle,
        )
        if teams_window is None:
            logger.warning(
                "Microsoft Teams window not found. Current automation cycle skipped."
            )
            logger.info("Application remains active.")
            return CycleResult.SKIPPED

        logger.info("Microsoft Teams window found: '%s'", teams_window.title)
        logger.info("Switching to Microsoft Teams")

        teams_session_active = False
        try:
            teams_attempts = int(timing.get("teams_activation_attempts", 3))
            teams_retry_delay = float(
                timing.get("teams_activation_retry_delay_seconds", 0.3)
            )
            teams_activated = self._window_manager.activate_window_with_retries(
                teams_window,
                attempts=teams_attempts,
                delay_seconds=teams_retry_delay,
            )
            if not teams_activated:
                logger.error(
                    "Unable to activate Microsoft Teams. Click cancelled. "
                    "Current foreground: '%s'",
                    self._window_manager.get_foreground_title(),
                )
                return CycleResult.SKIPPED

            teams_session_active = True

            activation_delay = float(timing["teams_activation_delay_seconds"])
            if activation_delay > 0:
                self._interruptible_sleep(activation_delay)

            if self._user_activity_detected_during_preparation(idle_monitor, idle_state):
                logger.info(
                    "User activity detected during automation preparation. "
                    "Current click cancelled."
                )
                return CycleResult.CANCELLED

            if not self._window_manager.is_foreground_window(teams_window):
                foreground_title = self._window_manager.get_foreground_title()
                logger.error(
                    "Microsoft Teams foreground verification failed. Click cancelled. "
                    "Current foreground: '%s'",
                    foreground_title,
                )
                return CycleResult.SKIPPED

            logger.info("Microsoft Teams verified as foreground")

            if self._user_activity_detected_during_preparation(idle_monitor, idle_state):
                logger.info(
                    "User activity detected during automation preparation. "
                    "Current click cancelled."
                )
                return CycleResult.CANCELLED

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

            logger.info("Automation cycle #%s completed", cycle_number)
            return CycleResult.COMPLETED
        finally:
            if teams_session_active:
                self._switch_back_to_youtube(
                    youtube_keywords,
                    youtube_window=youtube_window,
                    teams_window=teams_window,
                )

    def _user_activity_detected_during_preparation(
        self,
        idle_monitor: IdleMonitor | None,
        idle_state: IdleAutomationState | None,
    ) -> bool:
        if idle_monitor is None or idle_state is None:
            return False

        try:
            current_input_tick = idle_monitor.get_last_input_tick()
        except IdleDetectionError:
            return False

        return idle_state.has_user_activity_since_automation_started(current_input_tick)

    def _switch_back_to_youtube(
        self,
        youtube_keywords: list[str],
        *,
        youtube_window: WindowInfo | None = None,
        teams_window: WindowInfo | None = None,
    ) -> None:
        """Activate the existing YouTube window when available."""
        logger.info("Starting YouTube restore sequence")

        target_window = youtube_window
        if target_window is not None and not self._window_manager.is_window_handle_valid(
            target_window.handle
        ):
            target_window = None

        if target_window is None:
            target_window = self._window_manager.find_window_by_keywords(youtube_keywords)

        if target_window is None:
            logger.warning(
                "YouTube window not found. Unable to restore YouTube automatically. "
                "Check windows.youtube.title_keywords (browser tab title must contain a keyword)."
            )
            return

        timing = self._config.get("timing") or {}
        windows_config = self._config.get("windows") or {}
        youtube_config = windows_config.get("youtube") or {}
        attempts = int(timing.get("youtube_activation_attempts", 2))
        retry_delay = float(timing.get("youtube_activation_retry_delay_seconds", 0.2))
        settle_delay = float(timing.get("youtube_activation_delay_seconds", 0.3))
        restore_timeout = float(timing.get("youtube_restore_timeout_seconds", 6.0))
        minimize_teams = bool(youtube_config.get("restore_minimize_teams", False))
        deadline = time.monotonic() + max(1.0, restore_timeout)

        logger.info(
            "Switching back to YouTube: '%s' (timeout %.1fs)",
            target_window.title,
            restore_timeout,
        )

        try:
            if minimize_teams and teams_window is not None:
                self._window_manager.minimize_window(teams_window)

            activated = self._window_manager.activate_window_with_retries(
                target_window,
                attempts=attempts,
                delay_seconds=retry_delay,
                deadline=deadline,
            )
            if not activated:
                logger.warning(
                    "YouTube may not be foreground after restore (current: '%s'). "
                    "Continuing without blocking.",
                    self._window_manager.get_foreground_title(),
                )

            remaining = deadline - time.monotonic()
            if settle_delay > 0 and remaining > 0:
                self._interruptible_sleep(min(settle_delay, remaining))

            self._reposition_mouse_on_youtube(target_window)
        finally:
            logger.info("YouTube restore sequence finished")

    def _reposition_mouse_on_youtube(self, youtube_window: WindowInfo) -> None:
        """Move the cursor to a random point inside the YouTube window (optional)."""
        cursor_config = self._config.get("youtube_cursor") or {}
        if not cursor_config.get("enabled", True):
            return

        margin_pixels = int(cursor_config.get("margin_pixels", 80))

        try:
            rect = self._window_manager.get_window_rect(youtube_window)
        except RecoverableAutomationError as exc:
            logger.warning("Skipping YouTube cursor reposition: %s", exc)
            return

        point = random_point_in_rectangle(rect, margin_pixels)
        if point is None:
            logger.warning(
                "YouTube window is too small for cursor reposition "
                "(margin_pixels=%s).",
                margin_pixels,
            )
            return

        move_x, move_y = point
        try:
            self._window_manager.move_cursor_to(move_x, move_y)
        except Exception as exc:
            logger.warning("YouTube cursor reposition failed: %s", exc)
            return

        logger.info(
            "Mouse repositioned on YouTube at x=%s, y=%s (margin=%s)",
            move_x,
            move_y,
            margin_pixels,
        )

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
