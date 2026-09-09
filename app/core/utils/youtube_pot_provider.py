import os
import sys
from pathlib import Path

from app.config import APP_DATA_PATH, RESOURCE_PATH


PROVIDER_DIRECTORY_NAME = "youtube-pot-provider"
PROVIDER_ENV_VAR = "VIDEO_CAPTIONER_BGUTIL_SERVER_HOME"


def _provider_server_candidates() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get(PROVIDER_ENV_VAR, "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    # Source installs keep the provider in application data so npm dependencies
    # never pollute the repository. Frozen releases may bundle the same server
    # directory under their PyInstaller resource root.
    candidates.append(APP_DATA_PATH / PROVIDER_DIRECTORY_NAME / "server")
    candidates.append(RESOURCE_PATH / PROVIDER_DIRECTORY_NAME / "server")
    if bundle_root := getattr(sys, "_MEIPASS", None):
        candidates.append(
            Path(bundle_root) / "resource" / PROVIDER_DIRECTORY_NAME / "server"
        )
    return candidates


def find_bgutil_server_home() -> Path | None:
    """Return a usable bgutil script-provider directory, if installed."""
    for candidate in _provider_server_candidates():
        script_path = candidate / "build" / "generate_once.js"
        node_modules = candidate / "node_modules"
        if script_path.is_file() and node_modules.is_dir():
            return candidate
    return None


def add_bgutil_extractor_args(options: dict) -> bool:
    """Configure yt-dlp's local PO-token script provider when available."""
    server_home = find_bgutil_server_home()
    if server_home is None:
        return False

    extractor_args = options.setdefault("extractor_args", {})
    provider_args = extractor_args.setdefault("youtubepot-bgutilscript", {})
    provider_args["server_home"] = [str(server_home)]
    return True
