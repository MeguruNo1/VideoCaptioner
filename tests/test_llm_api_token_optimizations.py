import unittest

from app.core.subtitle_processor.translate import (
    OpenAITranslator,
    TRANSLATION_CHUNK_MAX_JSON_CHARS,
    TRANSLATION_READABILITY_POLICY_VERSION,
)
from app.core.subtitle_processor.optimize import SubtitleOptimizer


class FakeCacheManager:
    def __init__(self, cached_result=None):
        self.cached_result = cached_result
        self.llm_get_calls = []
        self.llm_set_calls = []
        self.translation_get_calls = []
        self.translation_set_calls = []

    def get_llm_result(self, prompt, model_name, **params):
        self.llm_get_calls.append((prompt, model_name, params))
        return self.cached_result

    def set_llm_result(self, prompt, result, model_name, **params):
        self.llm_set_calls.append((prompt, result, model_name, params))

    def get_translation(self, text, translator_type, **params):
        self.translation_get_calls.append((text, translator_type, params))
        return None

    def set_translation(self, text, translated_text, translator_type, **params):
        self.translation_set_calls.append(
            (text, translated_text, translator_type, params)
        )


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    usage = None

    def __init__(self, content):
        self.choices = [FakeChoice(content)]


def build_translator(cache_manager):
    translator = OpenAITranslator.__new__(OpenAITranslator)
    translator.model = "gpt-test"
    translator.target_language = "简体中文"
    translator.is_reflect = False
    translator.temperature = 0.7
    translator.batch_num = 10
    translator.batch_chunk_max_chars = TRANSLATION_CHUNK_MAX_JSON_CHARS
    translator.translation_max_length = 14
    translator.final_translation_rework_max_chars = 0
    translator.custom_prompt = ""
    translator.timeout = 300
    translator.use_cache = True
    translator.batch_context_enabled = True
    translator.batch_context_max_chars = 300
    translator.cache_manager = cache_manager
    translator.usage_callback = None
    return translator


class LLMAPITokenOptimizationTests(unittest.TestCase):
    def test_batch_translate_uses_cached_llm_result_without_api_call(self):
        translator = build_translator(
            FakeCacheManager(cached_result='{"1": "你好", "2": "世界"}')
        )

        def fail_api(*_, **__):
            raise AssertionError("API should not be called on cache hit")

        translator._call_api = fail_api

        result = translator._translate_chunk({"1": "hello", "2": "world"})

        self.assertEqual(result, {"1": "你好", "2": "世界"})
        self.assertEqual(len(translator.cache_manager.llm_get_calls), 1)
        self.assertEqual(translator.cache_manager.llm_set_calls, [])

    def test_cache_params_isolate_target_language_and_context_policy(self):
        cache_one = FakeCacheManager()
        first = build_translator(cache_one)
        first._call_api = lambda *_: FakeResponse('{"1": "你好"}')
        first._translate_chunk({"1": "hello"}, context_before="previous")

        cache_two = FakeCacheManager()
        second = build_translator(cache_two)
        second.target_language = "英语"
        second.batch_context_enabled = False
        second.batch_context_max_chars = 0
        second._call_api = lambda *_: FakeResponse('{"1": "hello"}')
        second._translate_chunk({"1": "你好"}, context_before="")

        first_params = cache_one.llm_get_calls[0][2]
        second_params = cache_two.llm_get_calls[0][2]

        self.assertNotEqual(
            first_params["target_language"], second_params["target_language"]
        )
        self.assertNotEqual(
            first_params["batch_context_enabled"],
            second_params["batch_context_enabled"],
        )
        self.assertNotEqual(
            first_params["batch_context_max_chars"],
            second_params["batch_context_max_chars"],
        )
        self.assertEqual(
            first_params["translation_readability_policy_version"],
            TRANSLATION_READABILITY_POLICY_VERSION,
        )

    def test_batch_translate_aligns_mismatched_keys_before_single_fallback(self):
        translator = build_translator(FakeCacheManager())
        translator._call_api = lambda *_: FakeResponse('{"0": "你好", "1": "世界"}')

        def fail_single(*_, **__):
            raise AssertionError("single-item fallback should not be used")

        translator._translate_chunk_single = fail_single

        result = translator._translate_chunk({"10": "hello", "11": "world"})

        self.assertEqual(result, {"10": "你好", "11": "世界"})
        self.assertEqual(len(translator.cache_manager.llm_set_calls), 1)

    def test_split_chunks_limits_json_payload_size(self):
        translator = build_translator(FakeCacheManager())
        translator.batch_num = 30
        translator.batch_chunk_max_chars = 140
        subtitle_dict = {
            "1": "short",
            "2": "x" * 80,
            "3": "y" * 80,
            "4": "tail",
        }

        chunks = translator._split_chunks(subtitle_dict)

        self.assertEqual(
            chunks,
            [
                {"1": "short", "2": "x" * 80},
                {"3": "y" * 80, "4": "tail"},
            ],
        )

    def test_zero_context_max_chars_disables_context_text(self):
        chunks = [{"1": "hello"}, {"2": "world"}]

        self.assertEqual(
            OpenAITranslator._build_chunk_context(chunks, 1, max_chars=0),
            "",
        )
        self.assertEqual(
            SubtitleOptimizer._build_chunk_context(chunks, 1, max_chars=0),
            "",
        )

    def test_length_instruction_is_soft_not_hard_limit(self):
        translator = build_translator(FakeCacheManager())
        translator.translation_max_length = 14

        instruction = translator._get_length_instruction()

        self.assertNotIn("不超过 14", instruction)
        self.assertIn("软约束", instruction)
        self.assertIn("可以超过", instruction)
        self.assertIn("不得省略", instruction)

    def test_zero_length_instruction_has_no_numeric_length_suggestion(self):
        translator = build_translator(FakeCacheManager())
        translator.translation_max_length = 0

        instruction = translator._get_length_instruction()

        self.assertNotIn("长度建议以", instruction)
        self.assertNotIn("不超过", instruction)
        self.assertIn("完整准确", instruction)

    def test_reading_budget_scales_with_subtitle_duration(self):
        translator = build_translator(FakeCacheManager())
        translator.translation_max_length = 14
        translator._subtitle_timing_by_key = {
            "1": {"duration_ms": 2000},
            "2": {"duration_ms": 5000},
            "3": {"duration_ms": 10000},
        }

        budgets = [
            translator._build_reading_budget(str(index))["suggested_length"]
            for index in range(1, 4)
        ]

        self.assertEqual(budgets, [24, 60, 120])

    def test_suspicious_compression_detects_missing_key_information(self):
        translator = build_translator(FakeCacheManager())
        subtitle_chunk = {
            "1": "The OpenAI API did not return 404 because the gateway retried twice."
        }
        translated = {"1": "网关重试了"}

        suspicious = translator._find_suspicious_compressions(
            subtitle_chunk, translated
        )

        self.assertIn("1", suspicious)
        self.assertTrue(
            any("numbers" in reason for reason in suspicious["1"]),
            suspicious["1"],
        )
        self.assertTrue(
            any("negation" in reason for reason in suspicious["1"]),
            suspicious["1"],
        )

    def test_empty_translation_is_suspicious(self):
        translator = build_translator(FakeCacheManager())

        suspicious = translator._find_suspicious_compressions(
            {"1": "hello"},
            {"1": ""},
        )

        self.assertIn("1", suspicious)
        self.assertIn("translated text is empty", suspicious["1"])

    def test_ten_as_chinese_word_is_not_reported_missing(self):
        translator = build_translator(FakeCacheManager())

        suspicious = translator._find_suspicious_compressions(
            {"1": "You promised 10 hours."},
            {"1": "你答应了十个小时。"},
        )

        reasons = suspicious.get("1", [])
        self.assertFalse(any("numbers" in reason for reason in reasons), reasons)

    def test_nine_out_of_ten_as_chinese_words_is_not_reported_missing(self):
        translator = build_translator(FakeCacheManager())

        suspicious = translator._find_suspicious_compressions(
            {"1": "I give it a 9 out of 10."},
            {"1": "我给它九分，满分十分。"},
        )

        reasons = suspicious.get("1", [])
        self.assertFalse(any("numbers" in reason for reason in reasons), reasons)

    def test_glossary_source_uses_word_boundaries(self):
        translator = build_translator(FakeCacheManager())
        translator.custom_prompt = "Wise -> 哲"

        suspicious = translator._find_suspicious_compressions(
            {"1": "Otherwise, this would change the meaning."},
            {"1": "否则，这会改变原意。"},
        )

        reasons = suspicious.get("1", [])
        self.assertFalse(any("custom prompt terms" in reason for reason in reasons))

    def test_glossary_target_satisfies_custom_term_check(self):
        translator = build_translator(FakeCacheManager())
        translator.custom_prompt = "Belle -> 铃"

        suspicious = translator._find_suspicious_compressions(
            {"1": "Belle made the decision."},
            {"1": "铃做出了决定。"},
        )

        reasons = suspicious.get("1", [])
        self.assertFalse(any("custom prompt terms" in reason for reason in reasons))

    def test_overlong_final_translation_retries_from_source_without_old_translation(self):
        translator = build_translator(FakeCacheManager())
        translator.use_cache = False
        translator.final_translation_rework_max_chars = 4
        calls = []

        def fake_call_api(prompt, user_content):
            calls.append((prompt, user_content))
            if len(calls) == 1:
                return FakeResponse('{"1": "这是一个超过阈值的很长译文"}')
            return FakeResponse("短译")

        translator._call_api = fake_call_api

        result = translator._translate_chunk({"1": "hello world"})

        self.assertEqual(result, {"1": "短译"})
        self.assertEqual(len(calls), 2)
        self.assertIn("hello world", calls[1][1])
        self.assertNotIn("这是一个超过阈值的很长译文", calls[1][1])
        self.assertIn("4", calls[1][1])

    def test_empty_single_translation_uses_source_without_caching(self):
        cache = FakeCacheManager()
        translator = build_translator(cache)
        translator._call_api = lambda *_: FakeResponse("<think>reasoning</think>")

        result = translator._translate_chunk_single({"1": "hello world"})

        self.assertEqual(result, {"1": "hello world"})
        self.assertEqual(cache.translation_set_calls, [])


if __name__ == "__main__":
    unittest.main()
