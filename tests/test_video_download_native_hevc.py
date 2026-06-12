import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.thread import video_download_thread


class _Progress:
    def __init__(self):
        self.events = []

    def emit(self, value, text):
        self.events.append((value, text))


class NativeHevcPostprocessTests(unittest.TestCase):
    def _thread(self):
        thread = video_download_thread.VideoDownloadThread.__new__(
            video_download_thread.VideoDownloadThread
        )
        thread.pr_smart_transcode_hevc_on_av1 = True
        thread.progress = _Progress()
        return thread

    def test_native_hevc_success_is_used_for_av1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "video.mp4"
            input_path.write_bytes(b"fake")

            with patch.object(
                video_download_thread, "is_native_hevc_transcode_supported", return_value=True
            ), patch.object(
                video_download_thread, "get_native_video_codec", return_value="av1"
            ), patch.object(
                video_download_thread,
                "transcode_video_to_hevc_native",
                return_value="macos_avfoundation_hevc",
            ) as transcode:
                result = self._thread()._postprocess_pr_smart_hevc(str(input_path))

            target_path, encoder, message, failed, fallback_source, fallback_target = result
            self.assertEqual(target_path, str(input_path.with_name("video-hevc.mp4")))
            self.assertEqual(encoder, "macos_avfoundation_hevc")
            self.assertIn("macOS 原生 API", message)
            self.assertFalse(failed)
            self.assertIsNone(fallback_source)
            self.assertIsNone(fallback_target)
            transcode.assert_called_once()

    def test_non_av1_does_not_trigger_native_transcode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "video.mp4"
            input_path.write_bytes(b"fake")

            with patch.object(
                video_download_thread, "is_native_hevc_transcode_supported", return_value=True
            ), patch.object(
                video_download_thread, "get_native_video_codec", return_value="h264"
            ), patch.object(
                video_download_thread, "transcode_video_to_hevc_native"
            ) as transcode:
                result = self._thread()._postprocess_pr_smart_hevc(str(input_path))

            self.assertEqual(result[2], "未触发，当前编码为 h264")
            self.assertFalse(result[3])
            transcode.assert_not_called()

    def test_native_failure_marks_manual_ffmpeg_fallback_without_calling_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "video.mp4"
            input_path.write_bytes(b"fake")

            with patch.object(
                video_download_thread, "is_native_hevc_transcode_supported", return_value=True
            ), patch.object(
                video_download_thread, "get_native_video_codec", return_value="av1"
            ), patch.object(
                video_download_thread,
                "transcode_video_to_hevc_native",
                side_effect=RuntimeError("native failed"),
            ), patch(
                "app.core.utils.video_utils.transcode_video_to_hevc"
            ) as ffmpeg_transcode:
                result = self._thread()._postprocess_pr_smart_hevc(str(input_path))

            self.assertIsNone(result[0])
            self.assertTrue(result[3])
            self.assertEqual(result[4], str(input_path))
            self.assertEqual(result[5], str(input_path.with_name("video-hevc.mp4")))
            self.assertIn("可手动使用 FFmpeg 重试", result[2])
            ffmpeg_transcode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
