# MacCleaner

A transparent, open-source Mac cleaning utility written in pure Python (tkinter).
Inspired by [AppCleaner](https://freemacsoft.net/appcleaner/), [OnyX](https://www.titanium-software.fr/en/onyx.html), and [Mole](https://github.com/tw93/Mole).

**Every deletion moves files to the macOS Trash — nothing is permanent.**
The full list of files is always shown before anything is removed.

---

## Features

| Panel | What it does |
|---|---|
| **App Uninstaller** | Picks apart an installed `.app` bundle, finds every support file it left in `~/Library` and `/Library`, and lets you move them all to Trash in one click. |
| **Cache Cleaner** | Lists everything in `~/Library/Caches` sorted by size so you can reclaim space quickly. |
| **Log Cleaner** | Lists log files in `~/Library/Logs` and `/private/var/log`. |
| **Orphan Finder** | Scans Library directories for entries whose bundle IDs (`com.*`, `io.*`, `org.*` …) don't match any currently installed app — leftovers from apps you've already deleted. |

### How app scanning works

1. Every `.app` in `/Applications` (and `~/Applications`) is parsed for its `CFBundleIdentifier` via `Contents/Info.plist`.
2. For a selected app, MacCleaner searches these locations for any entry whose name contains the bundle ID or app name:

```
~/Library/Preferences              ~/Library/Application Support
~/Library/Caches                   ~/Library/Logs
~/Library/Saved Application State  ~/Library/Containers
~/Library/Group Containers         ~/Library/LaunchAgents
~/Library/WebKit                   ~/Library/HTTPStorages
~/Library/Cookies

/Library/Preferences               /Library/Application Support
/Library/Caches                    /Library/LaunchAgents
/Library/LaunchDaemons             /Library/PrivilegedHelperTools
```

3. Results are displayed in a grouped tree with file sizes **before** any action is taken.
4. You can delete all found files or select individual rows.

---

## Requirements

- **macOS** 13 Ventura or later (uses `osascript` + Finder Trash)
- **Python ≥ 3.9** with `tkinter`

| Python distribution | tkinter included? |
|---|---|
| `/usr/bin/python3` (system, 3.9) | ✅ Yes — works out of the box |
| Homebrew `python@3.11 / 3.12 / 3.13` | ✅ Yes |
| Homebrew `python@3.14` | ❌ Install separately: `brew install python-tk@3.14` |

No third-party pip packages are required.

---

## Installation & Usage

```bash
# 1. Clone or download
git clone <repo-url>  # or just copy the folder

# 2. Run
cd MacCleaner
bash launch.sh
```

Or directly:

```bash
/usr/bin/python3 main.py
```

---

## Project structure

```
MacCleaner/
├── main.py          # Application window, sidebar navigation, all UI panels
├── scanner.py       # App discovery, remnant detection, orphan finder, cache/log scanning
├── cleaner.py       # Moves files to Trash via osascript (safe, reversible)
├── utils.py         # format_size(), get_file_size()
├── launch.sh        # Launcher — auto-selects a Python that has tkinter
└── requirements.txt # No pip deps; documents stdlib modules and Python version needs
```

---

## Safety model

| Concern | How it's handled |
|---|---|
| Accidental permanent deletion | Every removal calls `osascript` → Finder → Trash. Nothing bypasses Trash. |
| Showing files before deleting | The file tree is always populated first. Delete buttons are disabled until a scan completes. |
| Apple system files | The orphan finder skips all `com.apple.*` entries to avoid flagging macOS internals. |
| Files needing admin rights | `/Library` items may fail silently if you're not an admin; the results dialog reports any failures. |
| False-positive orphans | The orphan finder only flags entries whose name matches a bundle-ID pattern AND has no corresponding installed app. Review carefully before deleting. |

---

## Limitations

- Scans `/Applications` and `~/Applications` only (not sandboxed App Store containers installed elsewhere).
- Does not scan for kernel extensions (`.kext`) — those require SIP interaction.
- `/Library` paths may require admin privileges to delete; user-level `~/Library` paths work without elevation.
- File sizes are approximated using `du -sk`; very large directories may take a few seconds to measure.

---

## Acknowledgements

Design inspired by:
- [AppCleaner](https://freemacsoft.net/appcleaner/) by FreeMacSoft
- [OnyX](https://www.titanium-software.fr/en/onyx.html) by Titanium Software
- [Mole](https://github.com/tw93/Mole) by tw93
