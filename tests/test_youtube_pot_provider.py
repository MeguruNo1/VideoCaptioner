from pathlib import Path
from unittest.mock import patch

from app.core.utils.youtube_pot_provider import (
    PROVIDER_ENV_VAR,
    add_bgutil_extractor_args,
    find_bgutil_server_home,
)


def _make_provider(root: Path) -> Path:
    server = root / "server"
    (server / "build").mkdir(parents=True)
    (server / "build" / "generate_once.js").write_text("", encoding="utf-8")
    (server / "node_modules").mkdir()
    return server


def test_environment_provider_path_takes_precedence(tmp_path):
    server = _make_provider(tmp_path / "custom-provider")

    with patch.dict("os.environ", {PROVIDER_ENV_VAR: str(server)}):
        assert find_bgutil_server_home() == server


def test_extractor_args_are_merged_without_losing_youtube_clients(tmp_path):
    server = _make_provider(tmp_path / "custom-provider")
    options = {"extractor_args": {"youtube": {"player_client": ["web"]}}}

    with patch.dict("os.environ", {PROVIDER_ENV_VAR: str(server)}):
        assert add_bgutil_extractor_args(options) is True

    assert options["extractor_args"]["youtube"] == {"player_client": ["web"]}
    assert options["extractor_args"]["youtubepot-bgutilscript"] == {
        "server_home": [str(server)]
    }
