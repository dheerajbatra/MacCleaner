#!/usr/bin/env bash
# MacCleaner launcher — picks a Python that has tkinter.
set -e
cd "$(dirname "$0")"

# Prefer system Python (has tkinter on macOS); fall back to whatever works.
for PY in /usr/bin/python3 python3; do
  if "$PY" -c "import tkinter" 2>/dev/null; then
    exec "$PY" main.py
  fi
done

echo "ERROR: No Python with tkinter found." >&2
echo "Fix:  brew install python-tk  (or use /usr/bin/python3)" >&2
exit 1
