import os
import subprocess
import sys
from pathlib import Path


def is_macos() -> bool:
    return sys.platform == "darwin"


def app_data_dir(app_name: str) -> Path:
    return Path.home() / "Library" / "Application Support" / app_name


def default_work_dir(app_name: str) -> Path:
    return Path.home() / "Movies" / app_name


def open_path(path: str | os.PathLike) -> bool:
    target = str(Path(path).expanduser())
    try:
        subprocess.run(["open", target], check=False)
        return True
    except Exception:
        return False
