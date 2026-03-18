"""
cleaner.py — safe file deletion via macOS Trash (osascript).

Every item is MOVED TO TRASH rather than permanently deleted so the
user can recover anything accidentally removed.
"""

import os
import subprocess
from typing import List, Tuple


class Cleaner:

    def delete_files(self, paths: List[str]) -> List[Tuple[str, bool, str]]:
        """
        Move each path to the Trash.

        Returns a list of (path, success, error_message) tuples.
        """
        results: List[Tuple[str, bool, str]] = []
        for path in paths:
            ok, msg = self._move_to_trash(path)
            results.append((path, ok, msg))
        return results

    # ------------------------------------------------------------------ #

    @staticmethod
    def _move_to_trash(path: str) -> Tuple[bool, str]:
        """Move a single path to the macOS Trash using osascript."""
        if not os.path.exists(path):
            return False, "Path does not exist"

        # osascript is the most reliable way to move to Trash on macOS
        # and works for both files and directories without requiring
        # any third-party libraries.
        script = f'tell application "Finder" to delete POSIX file "{path}"'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip() or "osascript error"
        except subprocess.TimeoutExpired:
            return False, "Timed out"
        except Exception as exc:
            return False, str(exc)
