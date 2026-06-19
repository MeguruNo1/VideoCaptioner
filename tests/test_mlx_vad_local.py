import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.core.bk_asr.mlx_workflow import detect_speech_ranges


class MlxVadLocalTests(unittest.TestCase):
    def test_detect_speech_ranges_prefers_local_silero_repository(self):
        torch = Mock()
        waveform = Mock()
        waveform.ndim = 1
        waveform.float.return_value = waveform
        torchaudio = Mock()
        torchaudio.load.return_value = (waveform, 16000)
        get_speech_timestamps = Mock(return_value=[])
        torch.hub.load.return_value = (
            Mock(),
            (get_speech_timestamps, None, None, None, None),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "hubconf.py").write_text("", encoding="utf-8")
            with patch.dict(
                "sys.modules", {"torch": torch, "torchaudio": torchaudio}
            ), patch("app.core.bk_asr.mlx_workflow.LOCAL_SILERO_REPO", repo):
                self.assertEqual(detect_speech_ranges("audio.wav"), [])

        torch.hub.load.assert_called_once_with(
            repo_or_dir=str(repo),
            model="silero_vad",
            source="local",
            force_reload=False,
            onnx=True,
            trust_repo=True,
        )


if __name__ == "__main__":
    unittest.main()
