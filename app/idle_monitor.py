"""Windows user idle detection via GetLastInputInfo."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from app.exceptions import IdleDetectionError, PlatformNotSupportedError

logger = logging.getLogger("youtube_teams_automation")

IS_WINDOWS = sys.platform == "win32"


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


class IdleMonitor:
    """Provides user idle duration using the native Windows GetLastInputInfo API."""

    def __init__(self) -> None:
        if not IS_WINDOWS:
            raise PlatformNotSupportedError(
                "User idle monitoring is only supported on Microsoft Windows."
            )

        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._last_input_info = LASTINPUTINFO()
        self._last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)

    def get_last_input_tick(self) -> int:
        """Return the Windows tick count of the latest user input event."""
        if not self._user32.GetLastInputInfo(ctypes.byref(self._last_input_info)):
            raise IdleDetectionError("GetLastInputInfo failed")

        return int(self._last_input_info.dwTime)

    def get_idle_seconds(self) -> float:
        """Return seconds since the latest keyboard or mouse user input."""
        last_input_tick = self.get_last_input_tick()
        current_tick = int(self._kernel32.GetTickCount())

        # GetTickCount wraps approximately every 49.7 days.
        elapsed_ms = (current_tick - last_input_tick) & 0xFFFFFFFF
        return elapsed_ms / 1000.0

    def is_idle(self, threshold_seconds: float) -> bool:
        """Return True when user idle time meets or exceeds the threshold."""
        return self.get_idle_seconds() >= threshold_seconds


class IdleAutomationState:
    """Tracks idle-period automation trigger state independent of Windows idle time."""

    def __init__(self) -> None:
        self.automation_in_progress = False
        self.automation_triggered_for_current_idle_period = False
        self._post_automation_input_tick: int | None = None
        self._automation_start_input_tick: int | None = None
        self._previous_input_tick: int | None = None

    def initialize(self, input_tick: int) -> None:
        """Seed state with the current Windows last-input tick."""
        self._previous_input_tick = input_tick

    def poll_for_activity_reset(self, current_input_tick: int) -> bool:
        """
        Detect genuine new user activity and reset idle-period trigger state.

        Returns True when activity caused a reset.
        """
        if self.automation_in_progress:
            return False

        activity_detected = False

        if self._post_automation_input_tick is not None:
            if current_input_tick != self._post_automation_input_tick:
                activity_detected = True
        elif (
            self._previous_input_tick is not None
            and current_input_tick != self._previous_input_tick
            and self.automation_triggered_for_current_idle_period
        ):
            activity_detected = True

        self._previous_input_tick = current_input_tick

        if activity_detected:
            self.reset_idle_period("New user activity detected")
            return True

        return False

    def should_trigger_automation(self, idle_seconds: float, threshold_seconds: float) -> bool:
        """Return True when automation is eligible for the current idle period."""
        if self.automation_in_progress:
            return False
        if self.automation_triggered_for_current_idle_period:
            return False
        return idle_seconds >= threshold_seconds

    def on_automation_started(self, input_tick: int) -> None:
        self.automation_in_progress = True
        self._automation_start_input_tick = input_tick

    def on_automation_completed(self, input_tick: int) -> None:
        self.automation_in_progress = False
        self.automation_triggered_for_current_idle_period = True
        self._post_automation_input_tick = input_tick
        self._automation_start_input_tick = None
        self._previous_input_tick = input_tick

    def on_automation_cancelled(self) -> None:
        self.automation_in_progress = False
        self._automation_start_input_tick = None

    def on_automation_skipped(self, input_tick: int) -> None:
        """Mark the current idle period processed after a non-click cycle attempt."""
        self.on_automation_completed(input_tick)

    def has_user_activity_since_automation_started(self, current_input_tick: int) -> bool:
        """Return True when user input changed during automation preparation."""
        if not self.automation_in_progress:
            return False
        if self._automation_start_input_tick is None:
            return False
        return current_input_tick != self._automation_start_input_tick

    def reset_idle_period(self, reason: str) -> None:
        logger.info(reason)
        logger.info("Idle automation state reset")
        self.automation_triggered_for_current_idle_period = False
        self._post_automation_input_tick = None
        self._automation_start_input_tick = None
