import os
import re
import plistlib
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple, Set

from utils import get_file_size


# Each entry: (path, display_category, hidden_only)
# hidden_only=True  → only scan entries whose name starts with '.'
#                     (used for the home directory to catch dotfiles like ~/.opencode)
LIBRARY_SEARCH_PATHS: List[Tuple[str, str, bool]] = [
    # ── User Library ──────────────────────────────────────────────────── #
    ("~/Library/Preferences",            "Preferences",               False),
    ("~/Library/Application Support",    "Application Support",       False),
    ("~/Library/Caches",                 "Caches",                    False),
    ("~/Library/Logs",                   "Logs",                      False),
    ("~/Library/Saved Application State","Saved State",               False),
    ("~/Library/Containers",             "Containers",                False),
    ("~/Library/Group Containers",       "Group Containers",          False),
    ("~/Library/LaunchAgents",           "Launch Agents",             False),
    ("~/Library/WebKit",                 "WebKit Data",               False),
    ("~/Library/HTTPStorages",           "HTTP Storages",             False),
    ("~/Library/Cookies",                "Cookies",                   False),
    # ── Home directory dotfiles (.cursor, .config/…, etc.) ── #
    ("~",                                "Home Dotfiles (~/.name)",   True),
    ("~/.config",                        "Config (~/.config)",        False),
    ("~/.local/share",                   "Local Data (~/.local/share)", False),
    # ── System Library ────────────────────────────────────────────────── #
    ("/Library/Preferences",             "System Preferences",        False),
    ("/Library/Application Support",     "System App Support",        False),
    ("/Library/Caches",                  "System Caches",             False),
    ("/Library/LaunchAgents",            "System Launch Agents",      False),
    ("/Library/LaunchDaemons",           "Launch Daemons",            False),
    ("/Library/PrivilegedHelperTools",   "Privileged Helper Tools",   False),
]

# Bundle-ID TLD pattern — used by orphan finder
BUNDLE_ID_PATTERN = re.compile(
    r'^(com|net|org|io|co|app|pro|me|dev|uk|de|fr|jp)\.[a-z0-9]',
    re.IGNORECASE,
)


@dataclass
class AppInfo:
    name: str
    path: str
    bundle_id: Optional[str] = None
    version: Optional[str] = None
    size: int = 0


class AppScanner:
    # ------------------------------------------------------------------ #
    # Installed apps                                                       #
    # ------------------------------------------------------------------ #

    def get_installed_apps(self) -> List[AppInfo]:
        apps: List[AppInfo] = []
        for directory in ["/Applications", str(Path.home() / "Applications")]:
            if not os.path.isdir(directory):
                continue
            try:
                for entry in os.listdir(directory):
                    if entry.endswith(".app"):
                        info = self._parse_app_bundle(os.path.join(directory, entry))
                        if info:
                            apps.append(info)
            except PermissionError:
                pass
        return sorted(apps, key=lambda a: a.name.lower())

    def _parse_app_bundle(self, path: str) -> Optional[AppInfo]:
        name = os.path.basename(path).removesuffix(".app")
        bundle_id: Optional[str] = None
        version: Optional[str] = None

        info_plist = os.path.join(path, "Contents", "Info.plist")
        if os.path.exists(info_plist):
            try:
                with open(info_plist, "rb") as f:
                    plist = plistlib.load(f)
                bundle_id = plist.get("CFBundleIdentifier")
                version = (plist.get("CFBundleShortVersionString")
                           or plist.get("CFBundleVersion"))
                display = (plist.get("CFBundleDisplayName")
                           or plist.get("CFBundleName")
                           or name)
                name = display
            except Exception:
                pass

        return AppInfo(
            name=name, path=path,
            bundle_id=bundle_id, version=version,
            size=self._get_size(path),
        )

    # ------------------------------------------------------------------ #
    # Remnants for a specific installed app                                #
    # ------------------------------------------------------------------ #

    def find_app_remnants(self, app: AppInfo) -> Dict[str, List[str]]:
        """Return {category: [full_path, …]} for every support file found."""
        remnants: Dict[str, List[str]] = {}

        for base, category, hidden_only in LIBRARY_SEARCH_PATHS:
            expanded = os.path.expanduser(base)
            if not os.path.isdir(expanded):
                continue

            found: List[str] = []
            try:
                for entry in os.listdir(expanded):
                    if hidden_only and not entry.startswith("."):
                        continue
                    if self._entry_matches(entry, app):
                        found.append(os.path.join(expanded, entry))
            except PermissionError:
                continue

            if found:
                remnants[category] = found

        return remnants

    # ------------------------------------------------------------------ #
    # Precise per-entry matching                                           #
    # ------------------------------------------------------------------ #

    def _entry_matches(self, entry: str, app: AppInfo) -> bool:
        """
        Return True only if this directory/file entry clearly belongs to `app`.

        Strategy — avoid substring matching entirely to prevent false positives:
          • Bundle-ID entries  (com.company.App*): entry stem must START WITH the app's bundle ID.
          • Name-style entries (AppName/ or .appname): entry nodot must EXACTLY EQUAL a name variant.
        """
        entry_lower = entry.lower()
        nodot = entry_lower.lstrip(".")   # strip leading dot for dotfile matching

        # Strip the most common suffixes to get a comparable stem.
        stem = nodot
        for suffix in (".plist", ".savedstate", ".sfl3", ".sfl2", ".shipit"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break

        # ── 1. Bundle-ID prefix match ───────────────────────────────── #
        if app.bundle_id:
            bid = app.bundle_id.lower()
            # Accept exact match OR "com.app.Name.anything" (dot/dash separator)
            if stem == bid or stem.startswith(bid + ".") or stem.startswith(bid + "-"):
                return True
            # Same check on the raw nodot (before suffix stripping)
            if nodot == bid or nodot.startswith(bid + ".") or nodot.startswith(bid + "-"):
                return True

        # ── 2. App-name exact match ─────────────────────────────────── #
        # Only an exact case-insensitive match (with common spacing variants) is
        # accepted, so "opencode" never matches "claudefordesktop".
        for variant in self._name_variants(app.name):
            if nodot == variant or stem == variant:
                return True

        return False

    @staticmethod
    def _name_variants(name: str) -> Set[str]:
        variants: Set[str] = set()
        for v in [
            name,                       # "Brave Browser"
            name.replace(" ", ""),      # "BraveBrowser"
            name.replace(" ", "-"),     # "Brave-Browser"
            name.replace(" ", "_"),     # "Brave_Browser"
        ]:
            if len(v) > 3:
                variants.add(v.lower())
        return variants

    # ------------------------------------------------------------------ #
    # Orphan finder                                                        #
    # ------------------------------------------------------------------ #

    def find_orphaned_files(self) -> Dict[str, List[Tuple[str, int]]]:
        """Find Library entries that look like bundle IDs with no matching installed app."""
        installed_ids: Set[str] = {
            app.bundle_id.lower()
            for app in self.get_installed_apps()
            if app.bundle_id
        }

        orphans: Dict[str, List[Tuple[str, int]]] = {}

        for base, category, hidden_only in LIBRARY_SEARCH_PATHS:
            # Dotfile home-dir entries can't be reliably matched to bundle IDs
            if hidden_only:
                continue

            expanded = os.path.expanduser(base)
            if not os.path.isdir(expanded):
                continue

            found: List[Tuple[str, int]] = []
            try:
                for entry in os.listdir(expanded):
                    if not BUNDLE_ID_PATTERN.match(entry):
                        continue

                    stem = (entry
                            .removesuffix(".plist")
                            .removesuffix(".savedState")
                            .removesuffix(".sfl3")
                            .removesuffix(".sfl2"))
                    stem_lower = stem.lower()

                    # Skip Apple/macOS built-in entries
                    if stem_lower.startswith("com.apple."):
                        continue

                    matched = any(
                        stem_lower == bid
                        or stem_lower.startswith(bid + ".")
                        or bid.startswith(stem_lower + ".")
                        for bid in installed_ids
                    )
                    if not matched:
                        full = os.path.join(expanded, entry)
                        found.append((full, self._get_size(full)))
            except PermissionError:
                continue

            if found:
                orphans[category] = sorted(found, key=lambda x: x[1], reverse=True)

        return orphans

    # ------------------------------------------------------------------ #
    # Cache & log scanning                                                 #
    # ------------------------------------------------------------------ #

    def get_cache_files(self) -> Dict[str, List[Tuple[str, int]]]:
        return self._scan_dirs({"User Caches": os.path.expanduser("~/Library/Caches")})

    def get_log_files(self) -> Dict[str, List[Tuple[str, int]]]:
        return self._scan_dirs({
            "User Logs":   os.path.expanduser("~/Library/Logs"),
            "System Logs": "/private/var/log",
        })

    @staticmethod
    def _scan_dirs(targets: Dict[str, str]) -> Dict[str, List[Tuple[str, int]]]:
        result: Dict[str, List[Tuple[str, int]]] = {}
        for category, directory in targets.items():
            if not os.path.isdir(directory):
                continue
            files: List[Tuple[str, int]] = []
            try:
                for entry in os.listdir(directory):
                    full = os.path.join(directory, entry)
                    files.append((full, AppScanner._get_size(full)))
            except Exception:
                pass
            if files:
                result[category] = sorted(files, key=lambda x: x[1], reverse=True)
        return result

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_size(path: str) -> int:
        try:
            r = subprocess.run(["du", "-sk", path],
                               capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                return int(r.stdout.split()[0]) * 1024
        except Exception:
            pass
        try:
            return os.path.getsize(path)
        except Exception:
            return 0
