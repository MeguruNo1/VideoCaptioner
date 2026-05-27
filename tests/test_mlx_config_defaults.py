import unittest
from pathlib import Path

from app.common.config import TRANSCRIBE_MODEL_OPTIONS, cfg
from app.core.entities import TranscribeModelEnum


class MLXConfigDefaultsTests(unittest.TestCase):
    def test_mlx_whisper_is_available_in_transcribe_model_options(self):
        self.assertIn(TranscribeModelEnum.MLX_WHISPER, TRANSCRIBE_MODEL_OPTIONS)

    def test_mlx_config_uses_large_v3_turbo_with_word_timestamps(self):
        mlx_model = cfg.mlx_model.value
        if mlx_model.startswith("/"):
            model_path = Path(mlx_model)
            self.assertEqual(model_path.name, "mlx-whisper-large-v3-turbo")
            self.assertTrue((model_path / "config.json").exists())
            self.assertTrue((model_path / "weights.safetensors").exists())
        else:
            self.assertEqual(mlx_model, "mlx-community/whisper-large-v3-turbo")
        self.assertTrue(cfg.mlx_word_timestamps.value)
        self.assertEqual(cfg.mlx_hotwords.defaultValue, "")
        self.assertEqual(cfg.mlx_initial_prompt.defaultValue, "")


if __name__ == "__main__":
    unittest.main()
