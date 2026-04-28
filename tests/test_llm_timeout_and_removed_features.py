import sys
import unittest
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.entities import TranscribeConfig
from app.core.utils.openai_compat import get_openai_compat_request_options


class LLMTimeoutAndRemovedFeaturesTest(unittest.TestCase):
    def test_openai_compat_options_use_configurable_timeout(self):
        options = get_openai_compat_request_options(
            service_name="OpenAI",
            model_name="gpt-4o-mini",
            default_timeout=300,
        )
        self.assertEqual(options["timeout"], 300)
        self.assertNotIn("extra_body", options)

    def test_qwen_thinking_keeps_extra_body_without_timeout_override(self):
        options = get_openai_compat_request_options(
            service_name="Qwen",
            model_name="qwen-plus",
            qwen_enable_thinking=True,
            default_timeout=300,
        )
        self.assertEqual(options["timeout"], 300)
        self.assertEqual(options["extra_body"], {"enable_thinking": True})

    def test_deepseek_defaults_are_v4_models(self):
        config_source = (ROOT / "app" / "common" / "config.py").read_text(
            encoding="utf-8"
        )
        setting_source = (ROOT / "app" / "view" / "setting_interface.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"v4-pro"', config_source)
        self.assertIn('"v4-pro", "v4-flash"', setting_source)

    def test_whisperx_task_config_has_no_diarization_fields(self):
        field_names = {field.name for field in fields(TranscribeConfig)}
        self.assertNotIn("whisperx_diarize", field_names)
        self.assertNotIn("whisperx_local_diarize_dir", field_names)
        self.assertNotIn("whisperx_hf_token", field_names)


if __name__ == "__main__":
    unittest.main()
