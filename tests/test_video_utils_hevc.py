import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.utils import video_utils


class HevcTranscodeTests(unittest.TestCase):
    def test_mp4_normalization_copies_video_and_encodes_audio_to_aac(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.webm"
            output_path = Path(temp_dir) / "output.mp4"
            input_path.write_bytes(b"fake")

            def complete(command, **_kwargs):
                Path(command[-1]).write_bytes(b"mp4")
                return type("Result", (), {"returncode": 0, "stderr": ""})()

            with patch.object(video_utils.subprocess, "run", side_effect=complete) as run:
                result = video_utils.normalize_video_to_mp4(
                    str(input_path), str(output_path)
                )

            self.assertEqual(result, "stream_copy+aac")
            self.assertEqual(output_path.read_bytes(), b"mp4")
            command = run.call_args.args[0]
            self.assertIn("copy", command)
            self.assertIn("aac", command)

    def test_mp4_normalization_transcodes_when_stream_copy_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.webm"
            output_path = Path(temp_dir) / "output.mp4"
            input_path.write_bytes(b"fake")

            failed = type("Result", (), {"returncode": 1, "stderr": "unsupported"})()

            def transcode(_input, temp_output, **kwargs):
                Path(temp_output).write_bytes(b"hevc")
                self.assertTrue(kwargs["transcode_audio_to_aac"])
                return "hevc_videotoolbox"

            with patch.object(video_utils.subprocess, "run", return_value=failed), patch.object(
                video_utils, "transcode_video_to_hevc", side_effect=transcode
            ):
                result = video_utils.normalize_video_to_mp4(
                    str(input_path), str(output_path)
                )

            self.assertEqual(result, "hevc_videotoolbox+aac")
            self.assertEqual(output_path.read_bytes(), b"hevc")

    def test_mp4_normalization_forces_hevc_for_vp9_even_when_mp4_copy_might_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.mp4"
            output_path = Path(temp_dir) / "output.mp4"
            input_path.write_bytes(b"fake")

            def transcode(_input, temp_output, **kwargs):
                Path(temp_output).write_bytes(b"hevc")
                self.assertTrue(kwargs["transcode_audio_to_aac"])
                return "libx265"

            with patch.object(video_utils, "get_video_codec", return_value="vp9"), patch.object(
                video_utils.subprocess, "run"
            ) as run, patch.object(
                video_utils, "transcode_video_to_hevc", side_effect=transcode
            ):
                result = video_utils.normalize_video_to_mp4(
                    str(input_path),
                    str(output_path),
                    force_hevc_for_codecs={"vp9", "av1"},
                )

            self.assertEqual(result, "libx265+aac")
            self.assertEqual(output_path.read_bytes(), b"hevc")
            run.assert_not_called()

    def test_videotoolbox_decode_is_preferred_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.mp4"
            output_path = Path(temp_dir) / "output.mp4"
            input_path.write_bytes(b"fake")

            with patch.object(
                video_utils, "pick_hardware_hevc_encoder", return_value="hevc_videotoolbox"
            ), patch.object(
                video_utils, "_get_available_ffmpeg_hwaccels", return_value={"videotoolbox"}
            ), patch.object(
                video_utils, "_run_hevc_transcode_command"
            ) as run:
                result = video_utils.transcode_video_to_hevc(
                    str(input_path), str(output_path)
                )

            self.assertEqual(result, "hevc_videotoolbox+videotoolbox_decode")
            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertIn("-hwaccel", command)
            self.assertIn("videotoolbox", command)

    def test_videotoolbox_decode_failure_falls_back_to_regular_decode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.mp4"
            output_path = Path(temp_dir) / "output.mp4"
            input_path.write_bytes(b"fake")
            progress_events = []

            with patch.object(
                video_utils, "pick_hardware_hevc_encoder", return_value="hevc_videotoolbox"
            ), patch.object(
                video_utils, "_get_available_ffmpeg_hwaccels", return_value={"videotoolbox"}
            ), patch.object(
                video_utils,
                "_run_hevc_transcode_command",
                side_effect=[RuntimeError("hw decode failed"), None],
            ) as run:
                result = video_utils.transcode_video_to_hevc(
                    str(input_path),
                    str(output_path),
                    progress_callback=lambda value, text: progress_events.append(
                        (value, text)
                    ),
                )

            self.assertEqual(result, "hevc_videotoolbox")
            self.assertEqual(run.call_count, 2)
            first_command = run.call_args_list[0].args[0]
            second_command = run.call_args_list[1].args[0]
            self.assertIn("-hwaccel", first_command)
            self.assertNotIn("-hwaccel", second_command)
            self.assertIn(
                (
                    0,
                    "VideoToolbox 硬解 + HEVC 硬编失败，回退普通解码 + HEVC 硬编",
                ),
                progress_events,
            )

    def test_hardware_encode_failure_falls_back_to_libx265(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.mp4"
            output_path = Path(temp_dir) / "output.mp4"
            input_path.write_bytes(b"fake")

            with patch.object(
                video_utils, "pick_hardware_hevc_encoder", return_value="hevc_videotoolbox"
            ), patch.object(
                video_utils, "pick_software_hevc_encoder", return_value="libx265"
            ), patch.object(
                video_utils, "_get_available_ffmpeg_hwaccels", return_value=set()
            ), patch.object(
                video_utils,
                "_run_hevc_transcode_command",
                side_effect=[RuntimeError("hardware encode failed"), None],
            ) as run:
                result = video_utils.transcode_video_to_hevc(
                    str(input_path), str(output_path)
                )

            self.assertEqual(result, "libx265")
            self.assertEqual(run.call_count, 2)
            first_command = run.call_args_list[0].args[0]
            second_command = run.call_args_list[1].args[0]
            self.assertIn("hevc_videotoolbox", first_command)
            self.assertIn("libx265", second_command)


if __name__ == "__main__":
    unittest.main()
