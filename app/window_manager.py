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
from app.window_process import executable_matches_process_names
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

    def find_teams_window(self, teams_config: dict[str, Any]) -> WindowInfo | None:
        """Locate the main Microsoft Teams window by title and/or process name."""
        keywords = teams_config.get("title_keywords") or ["Microsoft Teams", "Teams"]
        process_names = teams_config.get("process_names") or ["ms-teams.exe", "Teams.exe"]
        min_width = int(teams_config.get("min_window_width", 100))
        min_height = int(teams_config.get("min_window_height", 80))
        include_minimized = bool(teams_config.get("include_minimized", True))

        window = self.find_window_by_keywords(
            keywords,
            min_width=min_width,
            min_height=min_height,
            include_minimized=include_minimized,
        )
        if window is not None:
            return window

        window = self.find_window_by_process_names(
            process_names,
            title_keywords=keywords,
            min_width=min_width,
            min_height=min_height,
            include_minimized=include_minimized,
        )
        if window is not None:
            logger.info(
                "Microsoft Teams window resolved by process name: '%s'",
                window.title,
            )
            return window

        logger.warning(
            "Microsoft Teams window not found. Open the Teams desktop app and verify "
            "windows.teams.title_keywords / windows.teams.process_names in config.yaml."
        )
        return None

    def find_window_by_keywords(
        self,
        keywords: Sequence[str],
        *,
        min_width: int = 0,
        min_height: int = 0,
        include_minimized: bool = False,
    ) -> WindowInfo | None:
        """Find the best window whose title contains any keyword (case-insensitive)."""
        if not keywords:
            return None

        normalized_keywords = [keyword for keyword in keywords if keyword]
        scored_matches: list[tuple[int, WindowInfo]] = []

        def callback(hwnd: int, _: Any) -> bool:
            if not self._is_top_level_window(hwnd):
                return True
            if not self._is_window_candidate(hwnd, include_minimized):
                return True

            title = self._win32gui.GetWindowText(hwnd)
            if not title:
                return True

            if not self._window_meets_min_size(hwnd, min_width, min_height):
                return True

            score = score_title_for_keywords(title, normalized_keywords)
            if score > 0:
                scored_matches.append((score, WindowInfo(handle=hwnd, title=title)))
            return True

        self._enum_windows(callback)
        return choose_best_scored_item(scored_matches)

    def find_window_by_process_names(
        self,
        process_names: Sequence[str],
        *,
        title_keywords: Sequence[str] = (),
        min_width: int = 0,
        min_height: int = 0,
        include_minimized: bool = False,
    ) -> WindowInfo | None:
        """Find the largest top-level window owned by a matching process."""
        if not process_names:
            return None

        normalized_process_names = [name for name in process_names if name]
        keyword_list = [keyword for keyword in title_keywords if keyword]
        best: tuple[tuple[int, int, int], WindowInfo] | None = None

        def callback(hwnd: int, _: Any) -> bool:
            nonlocal best
            if not self._is_top_level_window(hwnd):
                return True
            if not self._is_window_candidate(hwnd, include_minimized):
                return True
            if not self._window_meets_min_size(hwnd, min_width, min_height):
                return True

            process_id = self._window_process_id(hwnd)
            executable_name = self._process_executable_basename(process_id)
            if not executable_name or not executable_matches_process_names(
                executable_name,
                normalized_process_names,
            ):
                return True

            title = self._win32gui.GetWindowText(hwnd) or f"Teams ({executable_name})"
            keyword_score = score_title_for_keywords(title, keyword_list)
            area = self._window_area(hwnd)
            ranking = (keyword_score, area, int(hwnd))
            candidate = WindowInfo(handle=hwnd, title=title)
            if best is None or ranking > best[0]:
                best = (ranking, candidate)
            return True

        self._enum_windows(callback)
        return best[1] if best is not None else None

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

    def activate_window(self, window: WindowInfo) -> bool:
        """Bring a window to the foreground using a short, non-blocking Win32 sequence."""
        hwnd = window.handle
        if not self.is_window_handle_valid(hwnd):
            logger.error("Cannot activate destroyed window handle=%s", hwnd)
            return False

        try:
            self._allow_set_foreground()
            self._show_window(hwnd)
            self._win32gui.BringWindowToTop(hwnd)
        except Exception as exc:
            logger.error(
                "Failed to show window '%s' (handle=%s): %s",
                window.title,
                hwnd,
                exc,
            )
            return False

        self._set_foreground_safe(hwnd, window.title)
        return True

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
        attempts: int = 2,
        delay_seconds: float = 0.2,
        deadline: float | None = None,
    ) -> bool:
        """Activate a window with bounded retries (never blocks indefinitely)."""
        attempt_count = max(1, min(int(attempts), 3))
        delay = max(0.0, min(float(delay_seconds), 1.0))

        for attempt in range(1, attempt_count + 1):
            if deadline is not None and time.monotonic() >= deadline:
                logger.warning(
                    "Window activation timed out for '%s' before attempt %s",
                    window.title,
                    attempt,
                )
                break

            logger.info(
                "Window activation attempt %s/%s for '%s'",
                attempt,
                attempt_count,
                window.title,
            )
            self.activate_window(window)

            if self.is_foreground_window(window):
                logger.info(
                    "Window '%s' is foreground after attempt %s",
                    window.title,
                    attempt,
                )
                return True

            logger.info(
                "Window '%s' is not foreground yet (current: '%s')",
                window.title,
                self.get_foreground_title(),
            )
            if attempt < attempt_count and delay > 0:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(delay, remaining))
                else:
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

    def _set_foreground_safe(self, hwnd: int, title: str) -> None:
        """Set foreground; Windows often raises here — use a short Alt fallback."""
        try:
            self._win32gui.SetForegroundWindow(hwnd)
            return
        except Exception as exc:
            logger.warning(
                "SetForegroundWindow failed for '%s' (handle=%s): %s",
                title,
                hwnd,
                exc,
            )

        self._user32.keybd_event(VK_MENU, 0, 0, 0)
        try:
            self._win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:
            logger.warning(
                "SetForegroundWindow fallback failed for '%s' (handle=%s): %s",
                title,
                hwnd,
                exc,
            )
        finally:
            self._user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

    def _enum_windows(self, callback: Any) -> None:
        try:
            self._win32gui.EnumWindows(callback, None)
        except Exception as exc:
            raise RecoverableAutomationError(
                f"Window enumeration failed: {exc}"
            ) from exc

    def _is_top_level_window(self, hwnd: int) -> bool:
        if not self.is_window_handle_valid(hwnd):
            return False
        owner = self._win32gui.GetWindow(hwnd, self._win32con.GW_OWNER)
        return owner == 0

    def _is_window_candidate(self, hwnd: int, include_minimized: bool) -> bool:
        if self._win32gui.IsWindowVisible(hwnd):
            return True
        return include_minimized and bool(self._win32gui.IsIconic(hwnd))

    def _window_area(self, hwnd: int) -> int:
        try:
            left, top, right, bottom = self._win32gui.GetWindowRect(hwnd)
            return max(0, int(right) - int(left)) * max(0, int(bottom) - int(top))
        except Exception:
            return 0

    def _process_executable_basename(self, process_id: int) -> str | None:
        if process_id <= 0:
            return None

        process_handle = ctypes.windll.kernel32.OpenProcess(
            0x1000,
            False,
            int(process_id),
        )
        if not process_handle:
            return None

        try:
            buffer = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buffer))
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                process_handle,
                0,
                buffer,
                ctypes.byref(size),
            ):
                path = buffer.value
                if path:
                    return path.rsplit("\\", 1)[-1]
        finally:
            ctypes.windll.kernel32.CloseHandle(process_handle)

        return None

    def _window_meets_min_size(
        self,
        hwnd: int,
        min_width: int,
        min_height: int,
    ) -> bool:
        if min_width <= 0 and min_height <= 0:
            return True

        try:
            left, top, right, bottom = self._win32gui.GetWindowRect(hwnd)
            width = int(right) - int(left)
            height = int(bottom) - int(top)
        except Exception:
            return False

        if min_width > 0 and width < min_width:
            return False
        if min_height > 0 and height < min_height:
            return False
        return True

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
