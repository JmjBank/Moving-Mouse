"""Window enumeration, activation, and foreground verification."""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Sequence

from app.exceptions import PlatformNotSupportedError, RecoverableAutomationError
from app.window_selection import choose_best_scored_item, score_title_for_keywords

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
        import win32process  # type: ignore[import-untyped]

        self._win32con = win32con
        self._win32gui = win32gui
        self._win32process = win32process
        self._user32 = ctypes.windll.user32

    def find_window_by_keywords(self, keywords: Sequence[str]) -> WindowInfo | None:
        """Find the best visible window whose title contains any keyword (case-insensitive)."""
        if not keywords:
            return None

        normalized_keywords = [keyword for keyword in keywords if keyword]
        scored_matches: list[tuple[int, WindowInfo]] = []

        def callback(hwnd: int, _: Any) -> bool:
            if not self._win32gui.IsWindowVisible(hwnd):
                return True

            title = self._win32gui.GetWindowText(hwnd)
            if not title:
                return True

            score = score_title_for_keywords(title, normalized_keywords)
            if score > 0:
                scored_matches.append((score, WindowInfo(handle=hwnd, title=title)))
            return True

        try:
            self._win32gui.EnumWindows(callback, None)
        except Exception as exc:
            raise RecoverableAutomationError(
                f"Window enumeration failed: {exc}"
            ) from exc

        return choose_best_scored_item(scored_matches)

    def activate_window(self, window: WindowInfo) -> bool:
        """Bring a window to the foreground with Win32 focus workarounds."""
        hwnd = window.handle
        try:
            self._allow_set_foreground()
            self._show_window(hwnd)

            foreground_hwnd = self._win32gui.GetForegroundWindow()
            foreground_thread = self._window_thread_id(foreground_hwnd)
            target_thread = self._window_thread_id(hwnd)
            attached = False

            if foreground_thread and target_thread and foreground_thread != target_thread:
                self._user32.AttachThreadInput(foreground_thread, target_thread, True)
                attached = True

            try:
                self._win32gui.SetForegroundWindow(hwnd)
                self._win32gui.BringWindowToTop(hwnd)
            finally:
                if attached:
                    self._user32.AttachThreadInput(
                        foreground_thread, target_thread, False
                    )

            return True
        except Exception as exc:
            logger.error(
                "Failed to activate window '%s' (handle=%s): %s",
                window.title,
                hwnd,
                exc,
            )
            return False

    def activate_window_with_retries(
        self,
        window: WindowInfo,
        *,
        attempts: int = 3,
        delay_seconds: float = 0.25,
    ) -> bool:
        """Activate a window and retry until it becomes foreground or attempts are exhausted."""
        attempt_count = max(1, int(attempts))
        delay = max(0.0, float(delay_seconds))
        activation_succeeded = False

        for attempt in range(1, attempt_count + 1):
            if self.activate_window(window):
                activation_succeeded = True
                if self.is_foreground_window(window):
                    return True

                logger.debug(
                    "Window '%s' activation attempt %s did not reach foreground yet",
                    window.title,
                    attempt,
                )
            elif attempt < attempt_count:
                logger.debug(
                    "Window '%s' activation attempt %s failed",
                    window.title,
                    attempt,
                )

            if attempt < attempt_count and delay > 0:
                time.sleep(delay)

        return activation_succeeded

    def is_foreground_window(self, window: WindowInfo) -> bool:
        """Return True when the given window (or its root) owns the foreground."""
        try:
            foreground_hwnd = self._win32gui.GetForegroundWindow()
            if foreground_hwnd == window.handle:
                return True

            foreground_root = self._root_window_handle(foreground_hwnd)
            target_root = self._root_window_handle(window.handle)
            if foreground_root and foreground_root == target_root:
                return True

            foreground_pid = self._window_process_id(foreground_hwnd)
            target_pid = self._window_process_id(window.handle)
            return (
                foreground_pid != 0
                and target_pid != 0
                and foreground_pid == target_pid
            )
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

    def get_window_rect(self, window: WindowInfo) -> tuple[int, int, int, int]:
        """Return screen coordinates (left, top, right, bottom) for a window."""
        try:
            left, top, right, bottom = self._win32gui.GetWindowRect(window.handle)
            return int(left), int(top), int(right), int(bottom)
        except Exception as exc:
            raise RecoverableAutomationError(
                f"Unable to read window bounds for '{window.title}': {exc}"
            ) from exc

    def _show_window(self, hwnd: int) -> None:
        if self._win32gui.IsIconic(hwnd):
            self._win32gui.ShowWindow(hwnd, self._win32con.SW_RESTORE)
        else:
            self._win32gui.ShowWindow(hwnd, self._win32con.SW_SHOW)

    def _allow_set_foreground(self) -> None:
        try:
            current_process_id = int(ctypes.windll.kernel32.GetCurrentProcessId())
            self._user32.AllowSetForegroundWindow(wintypes.DWORD(current_process_id))
        except Exception:
            # Best-effort; focus activation still attempts AttachThreadInput below.
            pass

    def _root_window_handle(self, hwnd: int) -> int:
        if not hwnd:
            return 0
        return int(self._win32gui.GetAncestor(hwnd, self._win32con.GA_ROOT))

    def _window_thread_id(self, hwnd: int) -> int:
        if not hwnd:
            return 0
        return int(self._win32process.GetWindowThreadProcessId(hwnd)[0])

    def _window_process_id(self, hwnd: int) -> int:
        if not hwnd:
            return 0
        return int(self._win32process.GetWindowThreadProcessId(hwnd)[1])
