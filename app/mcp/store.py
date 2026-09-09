"""Atomic task snapshots and process-shared locks (macOS/Linux)."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time

DEFAULT_ROOT = Path.home() / "Library/Application Support/VideoCaptioner/mcp"
DEFAULT_OUTPUT = Path.home() / "Movies/VideoCaptioner"


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path, blocking=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("VIDEOCAPTIONER_MCP_ROOT", DEFAULT_ROOT)).expanduser().resolve()

    def path(self, job_id):
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job ID")
        return self.root / "jobs" / f"{job_id}.json"

    def read(self, job_id):
        try:
            return json.loads(self.path(job_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError("Unknown job ID") from None

    def save(self, state):
        state["updated_at"] = time.time()
        atomic_json(self.path(state["job_id"]), state)

    @contextmanager
    def edit(self, job_id):
        with file_lock(self.path(job_id).with_suffix(".lock")):
            state = self.read(job_id)
            yield state
            self.save(state)
