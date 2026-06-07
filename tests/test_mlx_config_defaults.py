import unittest
from pathlib import Path

from app.common.config import TRANSCRIBE_MODEL_OPTIONS, cfg
from app.core.entities import TranscribeModelEnum
from app.core.utils.mlx_model_utils import (
    DEFAULT_LOCAL_MLX_MODEL_DIR,
    DEFAULT_MLX_MODEL,
    preferred_mlx_model,
    validate_mlx_model,
)


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
        self.assertTrue(cfg.mlx_vad_enabled.defaultValue)
        self.assertEqual(cfg.mlx_vad_threshold.defaultValue, 0.5)
        self.assertEqual(cfg.mlx_chunk_duration.defaultValue, 600)
        self.assertEqual(cfg.mlx_chunk_overlap.defaultValue, 30)

    def test_mlx_model_validation_accepts_remote_model_name(self):
        is_valid, message = validate_mlx_model(DEFAULT_MLX_MODEL)

        self.assertTrue(is_valid)
        self.assertIn("HuggingFace", message)

    def test_mlx_model_validation_rejects_missing_local_model(self):
        is_valid, message = validate_mlx_model("/tmp/not-a-videocaptioner-mlx-model")

        self.assertFalse(is_valid)
        self.assertIn("不存在", message)

    def test_preferred_mlx_model_uses_local_default_when_available(self):
        preferred = preferred_mlx_model(DEFAULT_MLX_MODEL)
        if DEFAULT_LOCAL_MLX_MODEL_DIR.exists():
            self.assertEqual(preferred, str(DEFAULT_LOCAL_MLX_MODEL_DIR))
        else:
            self.assertEqual(preferred, DEFAULT_MLX_MODEL)


if __name__ == "__main__":
    unittest.main()
