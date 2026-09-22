"""Pure helpers for matching Windows process executable names."""

from __future__ import annotations

from typing import Sequence


def executable_matches_process_names(
    executable_name: str,
    process_names: Sequence[str],
) -> bool:
    """Return True when ``executable_name`` matches any configured process basename."""
    normalized_executable = executable_name.strip().lower()
    if not normalized_executable:
        return False

    for process_name in process_names:
        normalized_process = process_name.strip().lower()
        if not normalized_process:
            continue
        if normalized_executable == normalized_process:
            return True
        if normalized_executable.endswith(f"\\{normalized_process}"):
            return True
    return False
