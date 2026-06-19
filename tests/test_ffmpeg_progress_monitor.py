import time
from unittest.mock import patch

from app.thread.video_download_thread import FfmpegProgressMonitor


def test_locating_payload_is_indeterminate_and_has_no_fake_percent():
    payloads = []
    monitor = FfmpegProgressMonitor([10], payloads.append)

    monitor._emit_locating()

    assert payloads[-1]["phase"] == "locating"
    assert payloads[-1]["indeterminate"] is True
    assert payloads[-1]["percent"] == ""
    assert payloads[-1]["status"] == "正在定位片段起点"


def test_progress_frames_accumulate_across_multiple_sections():
    payloads = []
    monitor = FfmpegProgressMonitor([10, 20], payloads.append)

    monitor._handle_frame(
        {
            "out_time_us": "5000000",
            "speed": "2.0x",
            "total_size": "1048576",
            "progress": "continue",
        }
    )
    assert payloads[-1]["phase"] == "processing"
    assert payloads[-1]["percent"] == "16.7"
    assert payloads[-1]["downloaded"] == "1.0MB"
    assert payloads[-1]["section_index"] == 1

    monitor._handle_frame(
        {
            "out_time_us": "10000000",
            "speed": "2.0x",
            "progress": "end",
        }
    )
    assert payloads[-1]["phase"] == "locating"
    assert payloads[-1]["section_index"] == 2

    monitor._handle_frame(
        {
            "out_time_us": "10000000",
            "speed": "1.0x",
            "progress": "continue",
        }
    )
    assert payloads[-1]["percent"] == "66.7"
    assert payloads[-1]["section_index"] == 2


def test_listener_failure_keeps_locating_heartbeat_without_ffmpeg_args():
    payloads = []
    monitor = FfmpegProgressMonitor([10], payloads.append)

    with patch("app.thread.video_download_thread.socket.socket", side_effect=OSError("blocked")):
        assert monitor.start() is False
        time.sleep(0.05)
        monitor.stop()

    assert monitor.progress_url is None
    assert payloads
    assert payloads[-1]["phase"] == "locating"
