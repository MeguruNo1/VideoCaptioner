import os
import subprocess
import sys
from pathlib import Path


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform == "win32"


def app_data_dir(app_name: str) -> Path:
    if is_macos():
        return Path.home() / "Library" / "Application Support" / app_name
    if is_windows():
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / app_name
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / app_name


def default_work_dir(app_name: str) -> Path:
    if is_macos():
        return Path.home() / "Movies" / app_name
    if is_windows():
        return Path.cwd() / "work-dir"
    return Path.home() / app_name


def open_path(path: str | os.PathLike) -> bool:
    target = str(Path(path).expanduser())
    try:
        if is_macos():
            subprocess.run(["open", target], check=False)
        elif is_windows():
            os.startfile(target)
        else:
            subprocess.run(["xdg-open", target], check=False)
        return True
    except Exception:
        return False


def subprocess_no_window_kwargs() -> dict:
    if is_windows() and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
