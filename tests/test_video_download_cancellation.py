import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from app.thread import video_download_thread
from app.thread.video_download_thread import (
    VideoDownloadThread,
    _build_ydl_options,
    _build_strategy_options,
    _clean_stale_partial_files,
    _extract_metadata_info,
    _pick_subtitle_item,
    _resolve_cookiefile_path,
    _stable_selected_format_selector,
)


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


def test_download_options_keep_partial_files_for_network_resume(tmp_path):
    with patch(
        "app.thread.video_download_thread.add_bgutil_extractor_args",
        return_value=False,
    ):
        options = _build_ydl_options("", tmp_path / "missing-cookies.txt")

    assert options["continuedl"] is True
    assert options["nopart"] is False
    assert options["retries"] == 10
    assert options["fragment_retries"] == 10
    assert options["file_access_retries"] == 3
    assert options["extractor_retries"] == 3
    assert options["socket_timeout"] == 30


def test_download_options_enable_local_pot_provider(tmp_path):
    def configure(options):
        options.setdefault("extractor_args", {})["youtubepot-bgutilscript"] = {
            "server_home": ["/test/provider/server"]
        }
        return True

    with patch(
        "app.thread.video_download_thread.add_bgutil_extractor_args",
        side_effect=configure,
    ):
        options = _build_ydl_options("", tmp_path / "missing-cookies.txt")

    assert "youtube" not in options.get("extractor_args", {})
    assert options["extractor_args"]["youtubepot-bgutilscript"] == {
        "server_home": ["/test/provider/server"]
    }


def test_metadata_retries_creator_when_authenticated_youtube_is_limited_to_1080p(
    tmp_path,
):
    cookie_path = tmp_path / "cookies.txt"
    cookie_path.write_text("cookies", encoding="utf-8")
    initial = {
        "extractor_key": "Youtube",
        "formats": [
            {"format_id": "301", "height": 1080, "vcodec": "avc1", "acodec": "mp4a"}
        ],
        "automatic_captions": {"en": [{"url": "https://example.test/en.vtt"}]},
    }
    high_resolution = {
        "extractor_key": "Youtube",
        "formats": [
            {"format_id": "315", "height": 2160, "vcodec": "vp9", "acodec": "none"}
        ],
    }
    returned_info = iter([initial, high_resolution])
    received_options = []

    class FakeYoutubeDL:
        def __init__(self, options):
            received_options.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, *_args, **_kwargs):
            return next(returned_info)

    with (
        patch.object(video_download_thread, "_build_ydl_options", return_value={}),
        patch.object(video_download_thread.yt_dlp, "YoutubeDL", FakeYoutubeDL),
    ):
        result = _extract_metadata_info(
            "https://www.youtube.com/watch?v=test", "", cookie_path, "单线程"
        )

    assert received_options[1]["extractor_args"]["youtube"]["player_client"] == [
        "default", "web_safari"
    ]
    assert result["formats"][0]["height"] == 2160
    assert result["automatic_captions"] == initial["automatic_captions"]
    assert result["_videocaptioner_youtube_player_client"] == "default,web_safari"


def test_metadata_keeps_initial_result_when_creator_does_not_improve_resolution(
    tmp_path,
):
    cookie_path = tmp_path / "cookies.txt"
    cookie_path.write_text("cookies", encoding="utf-8")
    initial = {
        "extractor_key": "Youtube",
        "formats": [
            {"format_id": "301", "height": 1080, "vcodec": "avc1", "acodec": "mp4a"}
        ],
    }
    returned_info = iter(
        [
            initial,
            {
                "extractor_key": "Youtube",
                "formats": [
                    {"format_id": "18", "height": 360, "vcodec": "avc1", "acodec": "mp4a"}
                ],
            },
        ]
    )

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, *_args, **_kwargs):
            return next(returned_info)

    with (
        patch.object(video_download_thread, "_build_ydl_options", return_value={}),
        patch.object(video_download_thread.yt_dlp, "YoutubeDL", FakeYoutubeDL),
    ):
        result = _extract_metadata_info(
            "https://www.youtube.com/watch?v=test", "", cookie_path, "单线程"
        )

    assert result is initial


def test_metadata_reports_proxy_risk_after_cookie_and_anonymous_auth_blocks(tmp_path):
    cookie_path = tmp_path / "cookies.txt"
    cookie_path.write_text("cookies", encoding="utf-8")

    class RejectingYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, *_args, **_kwargs):
            raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")

    with (
        patch.object(video_download_thread, "_build_ydl_options", return_value={}),
        patch.object(video_download_thread, "_refresh_configured_browser_cookies", return_value=False),
        patch.object(video_download_thread.yt_dlp, "YoutubeDL", RejectingYoutubeDL),
        pytest.raises(RuntimeError, match="代理出口"),
    ):
        _extract_metadata_info(
            "https://www.youtube.com/watch?v=test", "", cookie_path, "多线程"
        )


def test_duplicate_youtube_audio_id_uses_prefix_selector():
    info = {
        "formats": [
            {"format_id": "140", "language": "ar", "vcodec": "none"},
            {"format_id": "140", "language": "en-US", "vcodec": "none"},
        ]
    }

    assert _stable_selected_format_selector(info, "140", "audio") == (
        "ba[format_id^=140]"
    )


def test_unique_youtube_video_id_remains_exact():
    info = {"formats": [{"format_id": "401", "height": 2160, "acodec": "none"}]}

    assert _stable_selected_format_selector(info, "401", "video") == "401"


def test_multithread_strategy_keeps_full_retry_budget():
    options = _build_strategy_options("多线程")

    assert options["concurrent_fragment_downloads"] == 4
    assert options["retries"] == 10
    assert options["fragment_retries"] == 10


def test_missing_task_cookie_falls_back_to_shared_software_cookie(tmp_path):
    missing = tmp_path / "deleted-task" / "cookies.txt"
    with patch.object(video_download_thread, "APP_DATA_PATH", tmp_path / "app-data"):
        assert _resolve_cookiefile_path(str(missing)) == tmp_path / "app-data" / "cookies.txt"


def test_403_recovery_removes_only_stale_partial_files(tmp_path):
    part = tmp_path / "video.mp4.part"
    state = tmp_path / "video.mp4.ytdl"
    final = tmp_path / "video.mp4"
    unrelated = tmp_path / "notes.txt"
    for path in (part, state, final, unrelated):
        path.write_bytes(b"data")

    assert _clean_stale_partial_files(tmp_path) == 2
    assert not part.exists()
    assert not state.exists()
    assert final.exists()
    assert unrelated.exists()


def test_selected_english_subtitle_wins_over_video_original_language():
    info = {
        "automatic_captions": {
            "ru": [{"url": "https://example.test/ru.vtt", "ext": "vtt"}],
            "en": [{"url": "https://example.test/en.vtt", "ext": "vtt"}],
        }
    }

    url, extension = _pick_subtitle_item(info, "auto", "en")

    assert url == "https://example.test/en.vtt"
    assert extension == "vtt"


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


def test_request_resume_clears_pause_and_allows_future_pause_notice(tmp_path):
    thread = _make_thread(tmp_path / "current-download")
    thread._pause_event.set()
    thread._pause_notice_emitted = True

    thread.request_resume()

    assert not thread._pause_event.is_set()
    assert thread._pause_notice_emitted is False


def test_restart_resume_reuses_completed_subtitle_and_transcript(tmp_path):
    title = "Resume Clip"
    work_dir = tmp_path / title
    subtitle_path = work_dir / "subtitle" / "【下载字幕】_en.vtt"
    transcript_path = work_dir / f"【视频文稿】{title}.txt"
    subtitle_path.parent.mkdir(parents=True)
    subtitle_path.write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nHello", encoding="utf-8")
    transcript_path.write_text("Hello", encoding="utf-8")
    info_dict = {
        "title": title,
        "automatic_captions": {
            "en": [{"url": "https://example.test/subtitle.vtt", "ext": "vtt"}]
        },
    }
    thread = VideoDownloadThread(
        url="https://example.test/video",
        work_dir=str(tmp_path),
        need_video=False,
        need_subtitle=True,
        need_transcript_txt=True,
        resume_existing=True,
    )

    with (
        patch.object(video_download_thread, "APP_DATA_PATH", tmp_path),
        patch.object(
            video_download_thread,
            "_extract_metadata_info",
            return_value=info_dict,
        ),
        patch.object(
            video_download_thread, "apply_download_proxy_environment", return_value=""
        ),
        patch.object(
            video_download_thread, "get_effective_download_proxy_url", return_value=""
        ),
        patch.object(video_download_thread, "_pick_subtitle_item") as pick_subtitle,
        patch.object(
            video_download_thread, "_download_subtitle_fallback"
        ) as download_subtitle,
        patch.object(thread, "_write_transcript_txt_file") as write_transcript,
        patch.object(video_download_thread.yt_dlp, "YoutubeDL") as youtube_dl,
    ):
        result = thread.download(
            need_video=False,
            need_subtitle=True,
            need_transcript_txt=True,
            resume_existing=True,
        )

    options = youtube_dl.call_args.args[0]
    assert options["writesubtitles"] is False
    assert options["writeautomaticsub"] is False
    assert result["subtitle_path"] == str(subtitle_path)
    assert result["transcript_txt_path"] == str(transcript_path)
    assert result["transcript_message"] == "已复用"
    pick_subtitle.assert_not_called()
    download_subtitle.assert_not_called()
    write_transcript.assert_not_called()


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
