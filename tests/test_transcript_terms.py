import sys
import types
import unittest
from unittest.mock import patch

from app.core.utils.transcript_terms import (
    apply_terms_to_document_prompt,
    apply_terms_to_mlx_hotwords,
    apply_terms_to_whisperx_hotwords,
    _build_hotword_translation_messages,
    _split_hotwords_by_glossary,
    GENERATED_TERMS_BEGIN,
    GENERATED_TERMS_END,
    extract_translation_terms_from_hotwords,
    filter_document_prompt_for_text,
    format_hotwords_from_terms,
    format_terms_for_document_prompt,
    merge_document_prompt,
    merge_hotwords,
    parse_ai_terms_response,
    parse_glossary_text,
    parse_hotwords_text,
    remove_generated_document_prompt_terms,
)


class TranscriptTermsTests(unittest.TestCase):
    def test_apply_terms_to_mlx_hotwords_does_not_touch_whisperx_hotwords(self):
        from app.common.config import cfg

        old_mlx_hotwords = cfg.mlx_hotwords.value
        old_whisperx_hotwords = cfg.whisperx_hotwords.value
        old_custom_prompt_text = cfg.custom_prompt_text.value
        with patch.object(cfg, "save", return_value=None):
            cfg.set(cfg.mlx_hotwords, "Existing")
            cfg.set(cfg.whisperx_hotwords, "WhisperXOnly")
            cfg.set(
                cfg.custom_prompt_text,
                f"keep\n{GENERATED_TERMS_BEGIN}\nold\n{GENERATED_TERMS_END}",
            )

            result = apply_terms_to_mlx_hotwords(
                [{"original": "MLX Whisper", "translation": "MLX Whisper"}]
            )

            self.assertEqual(result["mlx_hotwords"], "MLX Whisper")
            self.assertEqual(cfg.mlx_hotwords.value, "MLX Whisper")
            self.assertEqual(cfg.whisperx_hotwords.value, "WhisperXOnly")
            self.assertEqual(cfg.custom_prompt_text.value, "keep")

            cfg.set(cfg.mlx_hotwords, old_mlx_hotwords)
            cfg.set(cfg.whisperx_hotwords, old_whisperx_hotwords)
            cfg.set(cfg.custom_prompt_text, old_custom_prompt_text)

    def test_apply_terms_to_whisperx_hotwords_overwrites_existing_hotwords(self):
        from app.common.config import cfg

        old_mlx_hotwords = cfg.mlx_hotwords.value
        old_whisperx_hotwords = cfg.whisperx_hotwords.value
        old_custom_prompt_text = cfg.custom_prompt_text.value
        with patch.object(cfg, "save", return_value=None):
            cfg.set(cfg.mlx_hotwords, "MLXOnly")
            cfg.set(cfg.whisperx_hotwords, "Existing, Old")
            cfg.set(
                cfg.custom_prompt_text,
                f"keep\n{GENERATED_TERMS_BEGIN}\nold\n{GENERATED_TERMS_END}",
            )

            result = apply_terms_to_whisperx_hotwords(
                [
                    {"original": "WhisperX", "translation": "WhisperX"},
                    {"original": "whisperx", "translation": "duplicate"},
                    {"original": "VideoCaptioner", "translation": "视频字幕助手"},
                ]
            )

            self.assertEqual(result["whisperx_hotwords"], "WhisperX, VideoCaptioner")
            self.assertEqual(cfg.whisperx_hotwords.value, "WhisperX, VideoCaptioner")
            self.assertEqual(cfg.mlx_hotwords.value, "MLXOnly")
            self.assertEqual(cfg.custom_prompt_text.value, "keep")

            cfg.set(cfg.mlx_hotwords, old_mlx_hotwords)
            cfg.set(cfg.whisperx_hotwords, old_whisperx_hotwords)
            cfg.set(cfg.custom_prompt_text, old_custom_prompt_text)

    def test_parse_glossary_supports_common_separators(self):
        glossary = parse_glossary_text(
            "\n".join(
                [
                    "# comment",
                    "OpenAI -> 开放人工智能",
                    "WhisperX：WhisperX",
                    "VideoCaptioner = 视频字幕助手",
                ]
            )
        )

        self.assertEqual(glossary["openai"], "开放人工智能")
        self.assertEqual(glossary["whisperx"], "WhisperX")
        self.assertEqual(glossary["videocaptioner"], "视频字幕助手")

    def test_parse_ai_terms_response_prefers_glossary_translation(self):
        terms = parse_ai_terms_response(
            '{"terms":[{"original":"OpenAI","translation":"旧译名","category":"organization"}]}',
            "OpenAI -> 开放人工智能",
        )

        self.assertEqual(
            terms,
            [
                {
                    "original": "OpenAI",
                    "translation": "开放人工智能",
                    "category": "organization",
                }
            ],
        )

    def test_parse_ai_terms_response_prefers_fuzzy_glossary_translation(self):
        terms = parse_ai_terms_response(
            '{"terms":[{"original":"Zenless-Zone Zero","translation":"旧译名","category":"work"}]}',
            "Zenless Zone Zero -> 绝区零",
        )

        self.assertEqual(terms[0]["translation"], "绝区零")

    def test_parse_ai_terms_response_does_not_use_ambiguous_fuzzy_glossary_match(self):
        terms = parse_ai_terms_response(
            '{"terms":[{"original":"AB","translation":"AI译名","category":"term"}]}',
            "A-B -> 译名一\nA B -> 译名二",
        )

        self.assertEqual(terms[0]["translation"], "AI译名")

    def test_parse_ai_terms_response_does_not_collapse_programming_language_symbols(self):
        terms = parse_ai_terms_response(
            '{"terms":[{"original":"C#","translation":"AI译名","category":"term"}]}',
            "C++ -> C++",
        )

        self.assertEqual(terms[0]["translation"], "AI译名")

    def test_hotword_translation_prompt_includes_glossary_and_translation_rule(self):
        messages = _build_hotword_translation_messages(
            ["Zenless Zone Zero", "Belle"],
            "中文",
            "Zenless Zone Zero -> 绝区零\nBelle -> 铃",
        )
        prompt_text = "\n".join(message["content"] for message in messages)

        self.assertIn("Zenless Zone Zero -> 绝区零", prompt_text)
        self.assertIn("不要因为输入是英文专名就默认照抄为译名", prompt_text)

    def test_parse_ai_terms_response_uses_glossary_for_hotword_translation(self):
        terms = parse_ai_terms_response(
            '{"terms":[{"original":"Zenless Zone Zero","translation":"Zenless Zone Zero","category":"work"}]}',
            "Zenless Zone Zero -> 绝区零",
        )

        self.assertEqual(terms[0]["translation"], "绝区零")

    def test_split_hotwords_by_glossary_keeps_unmatched_for_ai(self):
        matched, unmatched = _split_hotwords_by_glossary(
            ["Zenless Zone Zero", "Belle", "Unknown"],
            "Zenless Zone Zero -> 绝区零\nBelle -> 铃",
        )

        self.assertEqual(
            matched,
            [
                {
                    "original": "Zenless Zone Zero",
                    "translation": "绝区零",
                    "category": "term",
                },
                {"original": "Belle", "translation": "铃", "category": "term"},
            ],
        )
        self.assertEqual(unmatched, ["Unknown"])

    def test_split_hotwords_by_glossary_uses_fuzzy_match(self):
        matched, unmatched = _split_hotwords_by_glossary(
            ["Zenless-Zone Zero", "Open AI"],
            "Zenless Zone Zero -> 绝区零\nOpenAI -> 开放人工智能",
        )

        self.assertEqual(
            matched,
            [
                {
                    "original": "Zenless-Zone Zero",
                    "translation": "绝区零",
                    "category": "term",
                },
                {
                    "original": "Open AI",
                    "translation": "开放人工智能",
                    "category": "term",
                },
            ],
        )
        self.assertEqual(unmatched, [])

    def test_extract_translation_terms_uses_glossary_without_llm_when_all_match(self):
        with patch(
            "app.core.utils.transcript_terms._resolve_current_llm_settings",
            side_effect=AssertionError("LLM should not be called"),
        ):
            terms = extract_translation_terms_from_hotwords(
                "Zenless Zone Zero, Belle",
                "简体中文",
                "Zenless Zone Zero -> 绝区零\nBelle -> 铃",
            )

        self.assertEqual(
            terms,
            [
                {
                    "original": "Zenless Zone Zero",
                    "translation": "绝区零",
                    "category": "term",
                },
                {"original": "Belle", "translation": "铃", "category": "term"},
            ],
        )

    def test_extract_translation_terms_sends_only_unmatched_hotwords_to_ai(self):
        captured = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured["messages"] = kwargs["messages"]
                return types.SimpleNamespace(
                    choices=[
                        types.SimpleNamespace(
                            message=types.SimpleNamespace(
                                content='{"terms":[{"original":"Unknown","translation":"未知","category":"term"}]}'
                            )
                        )
                    ]
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                pass

            chat = types.SimpleNamespace(
                completions=FakeCompletions(),
            )

        fake_openai_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.dict(sys.modules, {"openai": fake_openai_module}), patch(
            "app.core.utils.transcript_terms._resolve_current_llm_settings",
            return_value={
                "base_url": "https://example.test/v1",
                "api_key": "key",
                "model": "model",
                "service": "OpenAI",
                "timeout": 30,
                "qwen_enable_thinking": False,
            },
        ):
            terms = extract_translation_terms_from_hotwords(
                "Belle, Unknown, Zenless Zone Zero",
                "简体中文",
                "Belle -> 铃\nZenless Zone Zero -> 绝区零",
            )

        self.assertEqual(
            terms,
            [
                {"original": "Belle", "translation": "铃", "category": "term"},
                {"original": "Unknown", "translation": "未知", "category": "term"},
                {
                    "original": "Zenless Zone Zero",
                    "translation": "绝区零",
                    "category": "term",
                },
            ],
        )
        prompt_text = "\n".join(message["content"] for message in captured["messages"])
        self.assertIn("Belle -> 铃", prompt_text)
        self.assertIn("Zenless Zone Zero -> 绝区零", prompt_text)
        self.assertIn("- Unknown", prompt_text)
        self.assertNotIn("- Belle", prompt_text)
        self.assertNotIn("- Zenless Zone Zero", prompt_text)

    def test_merge_hotwords_preserves_existing_and_dedupes(self):
        hotwords = merge_hotwords(
            "OpenAI, Existing",
            [
                {"original": "openai", "translation": "开放人工智能"},
                {"original": "WhisperX", "translation": "WhisperX"},
            ],
        )

        self.assertEqual(hotwords, "OpenAI, Existing, WhisperX")

    def test_format_hotwords_from_terms_dedupes_without_existing_hotwords(self):
        hotwords = format_hotwords_from_terms(
            [
                {"original": "OpenAI", "translation": "开放人工智能"},
                {"original": "openai", "translation": "duplicate"},
                {"original": "WhisperX", "translation": "WhisperX"},
                {"original": "", "translation": "empty"},
            ],
        )

        self.assertEqual(hotwords, "OpenAI, WhisperX")

    def test_parse_hotwords_supports_common_separators_and_dedupes(self):
        hotwords = parse_hotwords_text("OpenAI， WhisperX; OpenAI\nVideoCaptioner")

        self.assertEqual(hotwords, ["OpenAI", "WhisperX", "VideoCaptioner"])

    def test_merge_document_prompt_replaces_generated_section(self):
        terms = [{"original": "OpenAI", "translation": "开放人工智能"}]
        prompt = merge_document_prompt("保留用户提示", terms)
        updated_prompt = merge_document_prompt(
            prompt,
            [{"original": "WhisperX", "translation": "WhisperX"}],
        )

        self.assertIn("保留用户提示", updated_prompt)
        self.assertNotIn("OpenAI -> 开放人工智能", updated_prompt)
        self.assertIn("WhisperX -> WhisperX", updated_prompt)
        self.assertEqual(updated_prompt.count(GENERATED_TERMS_BEGIN), 1)

    def test_apply_terms_to_document_prompt_replaces_previous_generated_terms(self):
        from app.common.config import cfg

        old_custom_prompt_text = cfg.custom_prompt_text.value
        with patch.object(cfg, "save", return_value=None):
            cfg.set(
                cfg.custom_prompt_text,
                merge_document_prompt(
                    "保留用户提示",
                    [{"original": "OpenAI", "translation": "开放人工智能"}],
                ),
            )

            result = apply_terms_to_document_prompt(
                [{"original": "WhisperX", "translation": "WhisperX"}]
            )

            self.assertIn("保留用户提示", result["custom_prompt_text"])
            self.assertNotIn("OpenAI -> 开放人工智能", result["custom_prompt_text"])
            self.assertIn("WhisperX -> WhisperX", result["custom_prompt_text"])
            self.assertEqual(result["custom_prompt_text"].count(GENERATED_TERMS_BEGIN), 1)

            cfg.set(cfg.custom_prompt_text, old_custom_prompt_text)

    def test_remove_generated_document_prompt_terms_preserves_user_prompt(self):
        prompt = merge_document_prompt(
            "保留用户提示",
            [{"original": "OpenAI", "translation": "开放人工智能"}],
        )

        self.assertEqual(
            remove_generated_document_prompt_terms(prompt),
            "保留用户提示",
        )

    def test_format_terms_for_document_prompt_skips_empty_original(self):
        prompt = format_terms_for_document_prompt(
            [
                {"original": "", "translation": "空"},
                {"original": "Term", "translation": ""},
            ]
        )

        self.assertIn("- Term", prompt)
        self.assertNotIn("空", prompt)
        self.assertIn("WhisperX 热词生成的翻译术语", prompt)

    def test_filter_document_prompt_keeps_only_matched_generated_terms(self):
        prompt = merge_document_prompt(
            "保留用户要求",
            [
                {"original": "OpenAI", "translation": "开放人工智能"},
                {"original": "WhisperX", "translation": "WhisperX"},
            ],
        )

        filtered = filter_document_prompt_for_text(prompt, "Today we use WhisperX.")

        self.assertIn("保留用户要求", filtered)
        self.assertIn("- WhisperX -> WhisperX", filtered)
        self.assertNotIn("OpenAI -> 开放人工智能", filtered)
        self.assertEqual(filtered.count(GENERATED_TERMS_BEGIN), 1)

    def test_filter_document_prompt_correction_keeps_unmatched_generated_terms(self):
        prompt = merge_document_prompt(
            "保留用户要求",
            [
                {"original": "Yixuan", "translation": "仪玄"},
                {"original": "Mr. Pan Yinhu", "translation": "潘引壶"},
            ],
        )

        filtered = filter_document_prompt_for_text(
            prompt,
            "Yee Xuan meets Mister Pan.",
            mode="correction",
        )

        self.assertIn("保留用户要求", filtered)
        self.assertIn("- Yixuan -> 仪玄", filtered)
        self.assertIn("- Mr. Pan Yinhu -> 潘引壶", filtered)
        self.assertEqual(filtered.count(GENERATED_TERMS_BEGIN), 1)

    def test_filter_document_prompt_translation_still_filters_unmatched_terms(self):
        prompt = merge_document_prompt(
            "保留用户要求",
            [
                {"original": "Yixuan", "translation": "仪玄"},
                {"original": "Yuzuha", "translation": "柚叶"},
            ],
        )

        filtered = filter_document_prompt_for_text(
            prompt,
            "Yuzuha appears in this subtitle.",
            mode="translation",
        )

        self.assertIn("- Yuzuha -> 柚叶", filtered)
        self.assertNotIn("- Yixuan -> 仪玄", filtered)

    def test_filter_document_prompt_removes_generated_block_when_no_terms_match(self):
        prompt = "\n".join(
            [
                "保留用户要求",
                GENERATED_TERMS_BEGIN,
                "AI 根据视频文稿提取的名称和术语，翻译与校正时优先遵循：",
                "- OpenAI -> 开放人工智能",
                GENERATED_TERMS_END,
            ]
        )

        filtered = filter_document_prompt_for_text(prompt, "unrelated subtitle")

        self.assertEqual(filtered, "保留用户要求")


if __name__ == "__main__":
    unittest.main()
