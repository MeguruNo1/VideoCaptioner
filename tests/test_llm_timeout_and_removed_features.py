import sys
import types
import unittest
from unittest.mock import patch
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("retry", types.ModuleType("retry"))

from app.common.config import cfg
from app.core.entities import TranscribeConfig
from app.core.subtitle_processor.prompt import (
    PROMPT_OPTIMIZER,
    PROMPT_REFLECT_TRANSLATE,
    PROMPT_SINGLE_TRANSLATE,
    PROMPT_SPLIT_SENTENCE,
    PROMPT_SPLIT_SEMANTIC,
    PROMPT_TRANSLATE,
    SPLIT_PROMPT_SEMANTIC,
    SPLIT_PROMPT_SENTENCE,
    get_default_prompt_template,
    get_prompt_template,
    validate_prompt_template,
)
from app.core.subtitle_processor.translate import (
    OpenAITranslator,
    TranslatorFactory,
    TranslatorType,
)
from app.core.utils.openai_compat import get_openai_compat_request_options


class LLMTimeoutAndRemovedFeaturesTest(unittest.TestCase):
    def _set_config_temporarily(self, config_item, value):
        old_value = cfg.get(config_item)
        cfg.set(config_item, value)
        return old_value

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

    def test_experimental_full_script_translate_mode_removed(self):
        translate_source = (
            ROOT / "app" / "core" / "subtitle_processor" / "translate.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("LONG_" + "CONTEXT_TRANSLATE_ENV", translate_source)
        self.assertNotIn(
            "VIDEO_CAPTIONER_" + "LONG_" + "CONTEXT_TRANSLATE",
            translate_source,
        )
        self.assertNotIn("_translate_subtitle_" + "long_context", translate_source)

    def test_semantic_split_prompt_no_longer_preserves_speaker_marker(self):
        marker_rule = "如果文本中包含说话人标记"
        self.assertNotIn(marker_rule, SPLIT_PROMPT_SEMANTIC)
        self.assertIn(marker_rule, SPLIT_PROMPT_SENTENCE)

    def test_translation_length_limit_prompt_can_be_enabled(self):
        old_prompt = self._set_config_temporarily(cfg.prompt_translate, "")
        translator = OpenAITranslator.__new__(OpenAITranslator)
        try:
            translator.is_reflect = False
            translator.target_language = "简体中文"
            translator.custom_prompt = ""
            translator.translation_max_length = 14

            prompt = translator._get_translate_prompt()

            self.assertIn("字幕阅读速度要求", prompt)
            self.assertIn("每条译文不超过 14 个字", prompt)
            self.assertIn("每条译文不超过 14 个词", prompt)
        finally:
            cfg.set(cfg.prompt_translate, old_prompt)

    def test_translation_length_limit_prompt_can_be_disabled(self):
        old_prompt = self._set_config_temporarily(cfg.prompt_translate, "")
        translator = OpenAITranslator.__new__(OpenAITranslator)
        try:
            translator.is_reflect = False
            translator.target_language = "简体中文"
            translator.custom_prompt = ""
            translator.translation_max_length = 0

            prompt = translator._get_translate_prompt()

            self.assertNotIn("字幕阅读速度要求", prompt)
            self.assertNotIn("每条译文不超过", prompt)
        finally:
            cfg.set(cfg.prompt_translate, old_prompt)

    def test_prompt_center_uses_default_when_override_is_empty(self):
        old_prompt = self._set_config_temporarily(cfg.prompt_split_semantic, "")
        try:
            self.assertEqual(
                get_prompt_template(PROMPT_SPLIT_SEMANTIC),
                get_default_prompt_template(PROMPT_SPLIT_SEMANTIC),
            )
        finally:
            cfg.set(cfg.prompt_split_semantic, old_prompt)

    def test_prompt_center_uses_custom_overrides(self):
        old_split = self._set_config_temporarily(
            cfg.prompt_split_sentence,
            "custom split ${max_word_count_cjk} ${max_word_count_english}",
        )
        old_optimizer = self._set_config_temporarily(
            cfg.prompt_optimizer,
            "custom optimizer prompt",
        )
        old_translate = self._set_config_temporarily(
            cfg.prompt_translate,
            "custom translate ${target_language} ${custom_prompt} ${translation_length_instruction}",
        )
        old_reflect = self._set_config_temporarily(
            cfg.prompt_reflect_translate,
            "custom reflect ${target_language} ${custom_prompt} ${translation_length_instruction}",
        )
        old_single = self._set_config_temporarily(
            cfg.prompt_single_translate,
            "custom single ${target_language} ${translation_length_instruction}",
        )
        try:
            self.assertIn("custom split", get_prompt_template(PROMPT_SPLIT_SENTENCE))
            self.assertEqual(
                get_prompt_template(PROMPT_OPTIMIZER), "custom optimizer prompt"
            )
            self.assertIn("custom translate", get_prompt_template(PROMPT_TRANSLATE))
            self.assertIn(
                "custom reflect", get_prompt_template(PROMPT_REFLECT_TRANSLATE)
            )
            self.assertIn("custom single", get_prompt_template(PROMPT_SINGLE_TRANSLATE))
        finally:
            cfg.set(cfg.prompt_split_sentence, old_split)
            cfg.set(cfg.prompt_optimizer, old_optimizer)
            cfg.set(cfg.prompt_translate, old_translate)
            cfg.set(cfg.prompt_reflect_translate, old_reflect)
            cfg.set(cfg.prompt_single_translate, old_single)

    def test_prompt_center_validates_required_variables(self):
        self.assertEqual(
            validate_prompt_template(
                PROMPT_TRANSLATE,
                "${target_language} ${custom_prompt} ${translation_length_instruction}",
            ),
            [],
        )
        self.assertEqual(
            validate_prompt_template(PROMPT_TRANSLATE, "${target_language}"),
            ["custom_prompt", "translation_length_instruction"],
        )

    def test_prompt_center_restore_default_by_clearing_override(self):
        old_prompt = self._set_config_temporarily(
            cfg.prompt_split_semantic,
            "custom split ${max_word_count_cjk} ${max_word_count_english}",
        )
        try:
            self.assertIn("custom split", get_prompt_template(PROMPT_SPLIT_SEMANTIC))
            cfg.set(cfg.prompt_split_semantic, "")
            self.assertEqual(
                get_prompt_template(PROMPT_SPLIT_SEMANTIC),
                get_default_prompt_template(PROMPT_SPLIT_SEMANTIC),
            )
        finally:
            cfg.set(cfg.prompt_split_semantic, old_prompt)

    def test_subtitle_optimizer_does_not_accept_translation_length_limit(self):
        optimizer_source = (
            ROOT / "app" / "core" / "subtitle_processor" / "optimize.py"
        ).read_text(encoding="utf-8")
        init_signature = optimizer_source.split("def __init__(", 1)[1].split(
            "):", 1
        )[0]

        self.assertNotIn("translation_max_length", init_signature)

    def test_subtitle_thread_passes_translation_length_only_to_translator(self):
        thread_source = (ROOT / "app" / "thread" / "subtitle_thread.py").read_text(
            encoding="utf-8"
        )
        optimizer_block = thread_source.split("optimizer = SubtitleOptimizer(", 1)[
            1
        ].split(")", 1)[0]
        translator_block = thread_source.split(
            "translator = TranslatorFactory.create_translator(", 1
        )[1].split(")", 1)[0]

        self.assertNotIn("translation_max_length", optimizer_block)
        self.assertIn(
            "translation_max_length=subtitle_config.translation_max_length",
            translator_block,
        )

    def test_translator_factory_passes_translation_length_to_openai_translator(self):
        with patch.object(OpenAITranslator, "_init_client", return_value=None):
            translator = TranslatorFactory.create_translator(
                translator_type=TranslatorType.OPENAI,
                translation_max_length=7,
            )

        self.assertIsInstance(translator, OpenAITranslator)
        self.assertEqual(translator.translation_max_length, 7)


if __name__ == "__main__":
    unittest.main()
