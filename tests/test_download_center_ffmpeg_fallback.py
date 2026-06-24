import unittest
from unittest.mock import patch

from app.view.download_center_interface import FfmpegHevcFallbackThread


class FfmpegHevcFallbackThreadTests(unittest.TestCase):
    def test_thread_calls_ffmpeg_transcode_only_when_run(self):
        completed = []
        errors = []
        thread = FfmpegHevcFallbackThread("source.mp4", "target.mp4")
        thread.completed.connect(lambda path, encoder: completed.append((path, encoder)))
        thread.error.connect(errors.append)

        with patch(
            "app.core.utils.video_utils.transcode_video_to_hevc",
            return_value="hevc_videotoolbox",
        ) as transcode:
            thread.run()

        transcode.assert_called_once()
        args, kwargs = transcode.call_args
        self.assertEqual(args, ("source.mp4", "target.mp4"))
        self.assertTrue(callable(kwargs.get("progress_callback")))
        self.assertTrue(kwargs.get("transcode_audio_to_aac"))
        self.assertEqual(completed, [("target.mp4", "hevc_videotoolbox")])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
