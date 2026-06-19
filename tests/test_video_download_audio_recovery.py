import json
import unittest
from unittest.mock import Mock, patch

from app.thread.video_download_thread import (
    _audio_repair_window,
    _media_has_valid_audio,
)


class VideoDownloadAudioRecoveryTests(unittest.TestCase):
    @patch("app.thread.video_download_thread.subprocess.run")
    def test_audio_stream_with_zero_duration_tag_is_invalid(self, run):
        run.return_value = Mock(
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "audio",
                            "duration": "3612.366",
                            "tags": {"DURATION": "00:00:00.000000000"},
                        }
                    ]
                }
            )
        )

        self.assertFalse(_media_has_valid_audio("broken.mkv"))

    @patch("app.thread.video_download_thread.subprocess.run")
    def test_positive_audio_duration_is_valid(self, run):
        run.return_value = Mock(
            stdout=json.dumps(
                {"streams": [{"codec_type": "audio", "duration": "10.25"}]}
            )
        )

        self.assertTrue(_media_has_valid_audio("valid.mp4"))

    @patch("app.thread.video_download_thread._probe_media_streams")
    def test_repair_window_accounts_for_video_keyframe_preroll(self, probe):
        probe.return_value = {"format": {"duration": "3612.366"}}

        start, duration = _audio_repair_window(
            "segment.mkv", ["*04:21:30-05:21:37"]
        )

        self.assertAlmostEqual(start, 15684.634, places=3)
        self.assertAlmostEqual(duration, 3612.366, places=3)


if __name__ == "__main__":
    unittest.main()
