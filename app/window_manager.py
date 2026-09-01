"""Window enumeration, activation, and foreground verification."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Sequence

from app.exceptions import PlatformNotSupportedError, RecoverableAutomationError

logger = logging.getLogger("youtube_teams_automation")

IS_WINDOWS = sys.platform.startswith("win")


@dataclass(frozen=True)
class WindowInfo:
    """Represents a located top-level window."""

    handle: int
    title: str


class WindowManager:
    """Find and control existing application windows."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        if not IS_WINDOWS:
            raise PlatformNotSupportedError(
                "Window automation is only supported on Microsoft Windows. "
                "Open YouTube and Microsoft Teams on Windows before running this application."
            )

        import win32con  # type: ignore[import-untyped]
        import win32gui  # type: ignore[import-untyped]

        self._win32con = win32con
        self._win32gui = win32gui

    def find_window_by_keywords(self, keywords: Sequence[str]) -> WindowInfo | None:
        """Find the first visible window whose title contains any keyword (case-insensitive)."""
        if not keywords:
            return None

        normalized_keywords = [keyword.lower() for keyword in keywords if keyword]
        matches: list[WindowInfo] = []

        def callback(hwnd: int, _: Any) -> bool:
            if not self._win32gui.IsWindowVisible(hwnd):
                return True

            title = self._win32gui.GetWindowText(hwnd)
            if not title:
                return True

            title_lower = title.lower()
            if any(keyword in title_lower for keyword in normalized_keywords):
                matches.append(WindowInfo(handle=hwnd, title=title))
            return True

        try:
            self._win32gui.EnumWindows(callback, None)
        except Exception as exc:
            raise RecoverableAutomationError(
                f"Window enumeration failed: {exc}"
            ) from exc

        if not matches:
            return None

        return matches[0]

    def activate_window(self, window: WindowInfo) -> bool:
        """Bring a window to the foreground. Returns True when activation was attempted."""
        hwnd = window.handle
        try:
            if self._win32gui.IsIconic(hwnd):
                self._win32gui.ShowWindow(hwnd, self._win32con.SW_RESTORE)
            else:
                self._win32gui.ShowWindow(hwnd, self._win32con.SW_SHOW)

            self._win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as exc:
            logger.error(
                "Failed to activate window '%s' (handle=%s): %s",
                window.title,
                hwnd,
                exc,
            )
            return False

    def is_foreground_window(self, window: WindowInfo) -> bool:
        """Return True when the given window is the current foreground window."""
        try:
            foreground_hwnd = self._win32gui.GetForegroundWindow()
            return foreground_hwnd == window.handle
        except Exception as exc:
            raise RecoverableAutomationError(
                f"Foreground verification failed: {exc}"
            ) from exc

    def get_foreground_title(self) -> str:
        """Return the title of the current foreground window (for diagnostics)."""
        try:
            hwnd = self._win32gui.GetForegroundWindow()
            return self._win32gui.GetWindowText(hwnd) or "<untitled>"
        except Exception:
            return "<unknown>"
