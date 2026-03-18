import os
import subprocess


def format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    elif size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_file_size(path: str) -> int:
    try:
        result = subprocess.run(
            ["du", "-sk", path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return int(result.stdout.split()[0]) * 1024
    except Exception:
        pass
    try:
        return os.path.getsize(path)
    except Exception:
        return 0
