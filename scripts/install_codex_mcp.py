#!/usr/bin/env python3
"""Install only this project's MCP entry and managed Skill; preserve other config."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import tempfile
import tomllib

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()
    home = (args.codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))).expanduser().absolute()
    codex = shutil.which("codex")
    if not codex:
        raise SystemExit("Codex CLI not found on PATH")
    if not importlib.util.find_spec("mcp"):
        raise SystemExit("Install requirements-mcp.txt in this Python environment first")
    python = os.path.abspath(sys.executable)
    script = str(PROJECT / "scripts/videocaptioner_mcp.py")
    config = home / "config.toml"
    original = config.read_text() if config.exists() else ""
    data = tomllib.loads(original) if original else {}
    existing = data.get("mcp_servers", {}).get("videocaptioner")
    if existing and (existing.get("command") != python or existing.get("args") != [script]):
        raise SystemExit("An unrelated videocaptioner MCP entry already exists; choose a different name before installing")
    source = PROJECT / "skills/videocaptioner"
    target = home / "skills/videocaptioner"
    marker = target / ".videocaptioner-managed"
    if target.exists() and not marker.is_file():
        raise SystemExit("An unmanaged videocaptioner Skill exists; it will not be overwritten")
    command = [codex, "mcp", "add", "videocaptioner", "--", python, script]
    print(json.dumps({"command": command, "skill_source": str(source), "skill_target": str(target),
                      "config": str(config), "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return
    home.mkdir(parents=True, exist_ok=True)
    if config.exists():
        shutil.copy2(config, config.with_name(f"config.toml.videocaptioner-{time.time_ns()}.bak"))
    if not existing:
        # Append exactly one TOML table. The CLI normalizes unrelated entries
        # (for example dropping empty args), so do not use it for the mutation.
        updated = original + "\n\n[mcp_servers.videocaptioner]\n" + f"command = {json.dumps(python)}\nargs = [{json.dumps(script)}]\n"
        parsed = tomllib.loads(updated)
        parsed["mcp_servers"].pop("videocaptioner")
        expected = dict(data)
        expected.setdefault("mcp_servers", {})
        if parsed != expected:
            raise SystemExit("Installation would change unrelated configuration")
        fd, temporary = tempfile.mkstemp(prefix=".config-videocaptioner-", dir=home)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, config)
        finally:
            Path(temporary).unlink(missing_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    marker.write_text(str(PROJECT) + "\n")
    print("Installed. Start a new Codex task or refresh MCP/Skills to discover videocaptioner.")


if __name__ == "__main__":
    main()
