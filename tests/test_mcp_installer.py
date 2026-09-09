from pathlib import Path
import subprocess
import sys
import tomllib

PROJECT = Path(__file__).resolve().parents[1]


def install(home, *extra):
    return subprocess.run([sys.executable, str(PROJECT / "scripts/install_codex_mcp.py"),
                           "--codex-home", str(home), *extra], capture_output=True, text=True)


def test_install_preserves_existing_text_and_is_repeatable(tmp_path):
    original = '# Keep comments and empty args\nmodel = "example"\n[mcp_servers.existing]\ncommand = "existing"\nargs = []\n'
    config = tmp_path / "config.toml"
    config.write_text(original)
    result = install(tmp_path)
    assert result.returncode == 0, result.stderr
    updated = config.read_text()
    assert updated.startswith(original)
    assert tomllib.loads(updated)["mcp_servers"]["existing"]["args"] == []
    assert (tmp_path / "skills/videocaptioner/SKILL.md").is_file()
    assert install(tmp_path).returncode == 0
    assert config.read_text() == updated


def test_dry_run_does_not_create_config_or_skill(tmp_path):
    result = install(tmp_path, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.iterdir())


def test_does_not_overwrite_conflicting_service(tmp_path):
    original = '[mcp_servers.videocaptioner]\ncommand = "another"\n'
    (tmp_path / "config.toml").write_text(original)
    result = install(tmp_path)
    assert result.returncode != 0
    assert (tmp_path / "config.toml").read_text() == original
