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

VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002


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

    def resolve_youtube_window(self, keywords: Sequence[str]) -> WindowInfo | None:
        """
        Prefer the current foreground window when it already looks like YouTube.

        This captures the browser the user was watching before automation switches away.
        """
        try:
            foreground_hwnd = self._win32gui.GetForegroundWindow()
        except Exception:
            foreground_hwnd = 0

        if foreground_hwnd and self.is_window_handle_valid(foreground_hwnd):
            title = self._win32gui.GetWindowText(foreground_hwnd) or ""
            if score_title_for_keywords(title, keywords) > 0:
                logger.info(
                    "Using current foreground window as YouTube target: '%s'",
                    title,
                )
                return WindowInfo(handle=foreground_hwnd, title=title)

        return self.find_window_by_keywords(keywords)

    def is_window_handle_valid(self, hwnd: int) -> bool:
        try:
            return bool(hwnd) and bool(self._win32gui.IsWindow(hwnd))
        except Exception:
            return False

    def window_info_from_handle(self, hwnd: int) -> WindowInfo | None:
        if not self.is_window_handle_valid(hwnd):
            return None
        title = self._win32gui.GetWindowText(hwnd) or "<untitled>"
        return WindowInfo(handle=hwnd, title=title)

    def activate_window(
        self,
        window: WindowInfo,
        *,
        minimize_blocking_window: bool = False,
    ) -> bool:
        """Bring a window to the foreground without AttachThreadInput (avoids deadlocks)."""
        hwnd = window.handle
        if not self.is_window_handle_valid(hwnd):
            logger.error("Cannot activate destroyed window handle=%s", hwnd)
            return False

        try:
            self._allow_set_foreground()
            if minimize_blocking_window:
                self._minimize_foreground_if_different(hwnd)

            self._show_window(hwnd)
            self._force_foreground(hwnd)
            return True
        except Exception as exc:
            logger.error(
                "Failed to activate window '%s' (handle=%s): %s",
                window.title,
                hwnd,
                exc,
            )
            return False

    def minimize_window(self, window: WindowInfo) -> bool:
        """Minimize a top-level window."""
        if not self.is_window_handle_valid(window.handle):
            return False

        try:
            self._win32gui.ShowWindow(window.handle, self._win32con.SW_MINIMIZE)
            return True
        except Exception as exc:
            logger.warning(
                "Failed to minimize window '%s' (handle=%s): %s",
                window.title,
                window.handle,
                exc,
            )
            return False

    def activate_window_with_retries(
        self,
        window: WindowInfo,
        *,
        attempts: int = 3,
        delay_seconds: float = 0.25,
        minimize_blocking_window: bool = False,
        blocking_window: WindowInfo | None = None,
    ) -> bool:
        """Activate a window and retry until it becomes foreground or attempts are exhausted."""
        attempt_count = max(1, int(attempts))
        delay = max(0.0, float(delay_seconds))

        for attempt in range(1, attempt_count + 1):
            logger.info(
                "Window activation attempt %s/%s for '%s'",
                attempt,
                attempt_count,
                window.title,
            )

            if blocking_window is not None and attempt == 1:
                self.minimize_window(blocking_window)

            if self.activate_window(
                window,
                minimize_blocking_window=minimize_blocking_window,
            ) and self.is_foreground_window(window):
                logger.info("Window '%s' is foreground after attempt %s", window.title, attempt)
                return True

            logger.info(
                "Window '%s' is not foreground yet (current: '%s')",
                window.title,
                self.get_foreground_title(),
            )
            if attempt < attempt_count and delay > 0:
                time.sleep(delay)

        return self.is_foreground_window(window)

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

    def move_cursor_to(self, x: int, y: int) -> None:
        """Move the mouse cursor using Win32 SetCursorPos (non-blocking)."""
        if not self._user32.SetCursorPos(int(x), int(y)):
            raise OSError(f"SetCursorPos failed for x={x}, y={y}")

    def _show_window(self, hwnd: int) -> None:
        if self._win32gui.IsIconic(hwnd):
            self._win32gui.ShowWindow(hwnd, self._win32con.SW_RESTORE)
        else:
            self._win32gui.ShowWindow(hwnd, self._win32con.SW_SHOW)

    def _minimize_foreground_if_different(self, target_hwnd: int) -> None:
        foreground_hwnd = self._win32gui.GetForegroundWindow()
        if not foreground_hwnd or foreground_hwnd == target_hwnd:
            return
        if not self.is_window_handle_valid(foreground_hwnd):
            return
        try:
            self._win32gui.ShowWindow(foreground_hwnd, self._win32con.SW_MINIMIZE)
        except Exception as exc:
            logger.debug("Could not minimize foreground window: %s", exc)

    def _force_foreground(self, hwnd: int) -> None:
        """Apply common Win32 focus workarounds without AttachThreadInput."""
        self._user32.keybd_event(VK_MENU, 0, 0, 0)
        try:
            self._win32gui.BringWindowToTop(hwnd)
            self._win32gui.SetForegroundWindow(hwnd)
            self._user32.SwitchToThisWindow(hwnd, True)
        finally:
            self._user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

    def _allow_set_foreground(self) -> None:
        try:
            current_process_id = int(ctypes.windll.kernel32.GetCurrentProcessId())
            self._user32.AllowSetForegroundWindow(wintypes.DWORD(current_process_id))
        except Exception:
            pass

    def _root_window_handle(self, hwnd: int) -> int:
        if not hwnd:
            return 0
        return int(self._win32gui.GetAncestor(hwnd, self._win32con.GA_ROOT))

    def _window_process_id(self, hwnd: int) -> int:
        if not hwnd:
            return 0
        return int(self._win32process.GetWindowThreadProcessId(hwnd)[1])
