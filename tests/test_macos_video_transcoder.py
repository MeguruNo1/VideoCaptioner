import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.core.utils import macos_video_transcoder


class _FakeTrack:
    def __init__(self, descriptions):
        self._descriptions = descriptions

    def formatDescriptions(self):
        return self._descriptions


class _FakeAsset:
    def __init__(self, tracks):
        self._tracks = tracks

    def tracksWithMediaType_(self, _media_type):
        return self._tracks


class _FakeSession:
    def __init__(self, status, file_type, output_bytes=b"hevc"):
        self._status = status
        self._file_type = file_type
        self._output_bytes = output_bytes
        self._output_url = None

    def supportedFileTypes(self):
        return [self._file_type]

    def setOutputURL_(self, value):
        self._output_url = value

    def setOutputFileType_(self, _value):
        pass

    def exportAsynchronouslyWithCompletionHandler_(self, handler):
        Path(self._output_url).write_bytes(self._output_bytes)
        handler()

    def progress(self):
        return 1.0

    def status(self):
        return self._status

    def error(self):
        return None


class _FakeExportSessionFactory:
    def __init__(self, session):
        self._session = session

    def alloc(self):
        return self

    def initWithAsset_presetName_(self, _asset, _preset):
        return self._session


class MacOSVideoTranscoderTests(unittest.TestCase):
    def test_get_native_video_codec_maps_av1_fourcc(self):
        av = SimpleNamespace(AVMediaTypeVideo="video")
        cm = SimpleNamespace(CMFormatDescriptionGetMediaSubType=lambda _description: int.from_bytes(b"av01", "big"))
        foundation = SimpleNamespace()

        with patch.object(macos_video_transcoder.sys, "platform", "darwin"), patch.object(
            macos_video_transcoder, "_load_frameworks", return_value=(av, cm, foundation)
        ), patch.object(
            macos_video_transcoder,
            "_asset_for_path",
            return_value=_FakeAsset([_FakeTrack(["description"])]),
        ):
            self.assertEqual(macos_video_transcoder.get_native_video_codec("input.mp4"), "av1")

    def test_get_native_video_codec_maps_vp9_fourcc(self):
        av = SimpleNamespace(AVMediaTypeVideo="video")
        cm = SimpleNamespace(CMFormatDescriptionGetMediaSubType=lambda _description: int.from_bytes(b"vp09", "big"))
        foundation = SimpleNamespace()

        with patch.object(macos_video_transcoder.sys, "platform", "darwin"), patch.object(
            macos_video_transcoder, "_load_frameworks", return_value=(av, cm, foundation)
        ), patch.object(
            macos_video_transcoder,
            "_asset_for_path",
            return_value=_FakeAsset([_FakeTrack(["description"])]),
        ):
            self.assertEqual(macos_video_transcoder.get_native_video_codec("input.mp4"), "vp9")

    def test_transcode_video_to_hevc_native_exports_with_avfoundation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.mp4"
            output_path = Path(temp_dir) / "output.mp4"
            input_path.write_bytes(b"input")
            progress_events = []

            av = SimpleNamespace(
                AVAssetExportPresetHEVCHighestQuality="HEVC_HQ",
                AVFileTypeMPEG4="public.mpeg-4",
                AVAssetExportSessionStatusCompleted=3,
            )
            av.AVAssetExportSession = _FakeExportSessionFactory(
                _FakeSession(av.AVAssetExportSessionStatusCompleted, av.AVFileTypeMPEG4)
            )
            foundation = SimpleNamespace(NSURL=SimpleNamespace(fileURLWithPath_=lambda value: value))

            with patch.object(macos_video_transcoder.sys, "platform", "darwin"), patch.object(
                macos_video_transcoder, "_load_frameworks", return_value=(av, SimpleNamespace(), foundation)
            ), patch.object(
                macos_video_transcoder, "_asset_for_path", return_value=object()
            ):
                result = macos_video_transcoder.transcode_video_to_hevc_native(
                    str(input_path),
                    str(output_path),
                    progress_callback=lambda value, text: progress_events.append((value, text)),
                )

            self.assertEqual(result, "macos_avfoundation_hevc")
            self.assertTrue(output_path.is_file())
            self.assertIn((100, "H.265 转码完成"), progress_events)


if __name__ == "__main__":
    unittest.main()
