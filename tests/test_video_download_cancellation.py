import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.thread.video_download_thread import VideoDownloadThread


def _make_thread(download_dir: Path) -> VideoDownloadThread:
    thread = VideoDownloadThread.__new__(VideoDownloadThread)
    thread._terminate_event = threading.Event()
    thread._pause_event = threading.Event()
    thread._download_processes_done = threading.Event()
    thread._download_processes_done.set()
    thread._download_dir = download_dir
    thread._download_root = download_dir.parent
    thread._download_dir_existed = download_dir.exists()
    thread._download_started_at = time.time()
    thread._cleanup_lock = threading.Lock()
    thread._cleanup_completed = False
    thread._cleanup_message = ""
    return thread


def _make_process(pid: int, name: str, command: list[str]):
    process = MagicMock()
    process.pid = pid
    process.name.return_value = name
    process.cmdline.return_value = command
    return process


def test_request_terminate_stops_only_ffmpeg_for_current_download(tmp_path):
    download_dir = tmp_path / "current-download"
    thread = _make_thread(download_dir)
    thread._pause_event.set()

    current_ffmpeg = _make_process(
        101,
        "ffmpeg",
        ["ffmpeg", "-i", "https://example.test/video", f"file:{download_dir}/video.mkv.part"],
    )
    other_ffmpeg = _make_process(
        102,
        "ffmpeg",
        ["ffmpeg", "-i", "input.mp4", f"{tmp_path}/other/video.mp4"],
    )
    unrelated_process = _make_process(
        103,
        "python",
        ["python", str(download_dir / "worker.py")],
    )
    parent = MagicMock()
    parent.children.return_value = [current_ffmpeg, other_ffmpeg, unrelated_process]
    current_ffmpeg.terminate.side_effect = lambda: assert_termination_event_cleared(thread)

    with (
        patch("app.thread.video_download_thread.psutil.Process", return_value=parent),
        patch("app.thread.video_download_thread.threading.Thread") as cleanup_thread,
    ):
        thread.request_terminate()

    assert thread._terminate_event.is_set()
    assert not thread._pause_event.is_set()
    current_ffmpeg.terminate.assert_called_once_with()
    other_ffmpeg.terminate.assert_not_called()
    unrelated_process.terminate.assert_not_called()
    cleanup_thread.assert_called_once()
    cleanup_thread.return_value.start.assert_called_once_with()


def assert_termination_event_cleared(thread):
    assert not thread._download_processes_done.is_set()


def test_request_terminate_without_download_dir_only_sets_event():
    thread = _make_thread(Path("."))
    thread._download_dir = None

    with patch("app.thread.video_download_thread.psutil.Process") as process:
        thread.request_terminate()

    assert thread._terminate_event.is_set()
    process.assert_not_called()


def test_force_kills_ffmpeg_that_ignores_terminate():
    stopped = _make_process(201, "ffmpeg", ["ffmpeg"])
    alive = _make_process(202, "ffmpeg", ["ffmpeg"])

    with patch(
        "app.thread.video_download_thread.psutil.wait_procs",
        return_value=([stopped], [alive]),
    ):
        VideoDownloadThread._kill_download_subprocesses_after_timeout([stopped, alive])

    stopped.kill.assert_not_called()
    alive.kill.assert_called_once_with()


def test_cleanup_waits_for_download_processes_before_removing_files(tmp_path):
    download_dir = tmp_path / "current-download"
    download_dir.mkdir()
    partial = download_dir / "video.mkv.part"
    partial.write_bytes(b"partial")
    thread = _make_thread(download_dir)
    thread._download_dir_existed = False
    thread._download_processes_done.clear()

    cleanup_started = threading.Event()

    def cleanup():
        thread._wait_for_download_subprocesses()
        cleanup_started.set()
        thread._cleanup_partial_download("cancelled")

    worker = threading.Thread(target=cleanup)
    worker.start()
    time.sleep(0.05)
    assert not cleanup_started.is_set()
    assert partial.exists()

    thread._download_processes_done.set()
    worker.join(timeout=1)

    assert cleanup_started.is_set()
    assert not download_dir.exists()


def test_cleanup_is_idempotent_and_preserves_preexisting_files(tmp_path):
    download_dir = tmp_path / "current-download"
    download_dir.mkdir()
    old_file = download_dir / "keep.txt"
    old_file.write_text("keep")
    old_timestamp = time.time() - 60
    old_file.touch()
    os.utime(old_file, (old_timestamp, old_timestamp))
    thread = _make_thread(download_dir)
    thread._download_dir_existed = True
    partial = download_dir / "video.mkv.part"
    partial.write_bytes(b"partial")

    first_message = thread._cleanup_partial_download("cancelled")
    second_message = thread._cleanup_partial_download("cancelled again")

    assert old_file.exists()
    assert not partial.exists()
    assert second_message == first_message
