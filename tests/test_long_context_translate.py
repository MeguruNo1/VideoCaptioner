import json
import os
import sys
import types
import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BK_ASR_PACKAGE = "app.core.bk_asr"
ASR_DATA_MODULE = f"{BK_ASR_PACKAGE}.asr_data"

bk_asr_package = types.ModuleType(BK_ASR_PACKAGE)
bk_asr_package.__path__ = [str(ROOT / "app" / "core" / "bk_asr")]
sys.modules.setdefault(BK_ASR_PACKAGE, bk_asr_package)

asr_data_spec = importlib.util.spec_from_file_location(
    ASR_DATA_MODULE, ROOT / "app" / "core" / "bk_asr" / "asr_data.py"
)
asr_data_module = importlib.util.module_from_spec(asr_data_spec)
sys.modules[ASR_DATA_MODULE] = asr_data_module
asr_data_spec.loader.exec_module(asr_data_module)

ASRData = asr_data_module.ASRData
ASRDataSeg = asr_data_module.ASRDataSeg

from app.core.subtitle_processor.translate import (
    BaseTranslator,
    LONG_CONTEXT_TRANSLATE_ENV,
    OpenAITranslator,
)


def make_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def make_asr_data():
    return ASRData(
        [
            ASRDataSeg("hello", 0, 1000),
            ASRDataSeg("world", 1000, 2000),
            ASRDataSeg("again", 2000, 3000),
        ]
    )


def make_translator(response_content):
    translator = OpenAITranslator.__new__(OpenAITranslator)
    translator.thread_num = 1
    translator.batch_num = 10
    translator.target_language = "简体中文"
    translator.retry_times = 1
    translator.timeout = 60
    translator.is_running = True
    translator.update_callback = None
    translator.custom_prompt = ""
    translator.usage_callback = None
    translator.model = "mock-model"
    translator.is_reflect = False
    translator.temperature = 0.7
    translator._call_api = lambda prompt, user_content: make_response(response_content)
    return translator


class LongContextTranslateTest(unittest.TestCase):
    def test_long_context_translation_updates_segments(self):
        response_content = json.dumps(
            {"1": "你好", "2": "世界", "3": "再见"}, ensure_ascii=False
        )
        translator = make_translator(response_content)

        with patch.dict(os.environ, {LONG_CONTEXT_TRANSLATE_ENV: "1"}):
            result = translator.translate_subtitle(make_asr_data())

        self.assertEqual(
            [seg.translated_text for seg in result.segments],
            ["你好", "世界", "再见"],
        )
        self.assertEqual([seg.start_time for seg in result.segments], [0, 1000, 2000])

    def test_long_context_translation_falls_back_on_bad_response(self):
        translator = make_translator(json.dumps({"1": "你好"}, ensure_ascii=False))
        fallback_result = make_asr_data()

        with patch.object(
            BaseTranslator, "translate_subtitle", return_value=fallback_result
        ) as fallback_translate:
            with patch.dict(os.environ, {LONG_CONTEXT_TRANSLATE_ENV: "1"}):
                result = translator.translate_subtitle(make_asr_data())

        self.assertIs(result, fallback_result)
        fallback_translate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
