import unittest

from app.core.utils.transcript_terms import (
    GENERATED_TERMS_BEGIN,
    format_terms_for_document_prompt,
    merge_document_prompt,
    merge_hotwords,
    parse_ai_terms_response,
    parse_glossary_text,
)


class TranscriptTermsTests(unittest.TestCase):
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

    def test_merge_hotwords_preserves_existing_and_dedupes(self):
        hotwords = merge_hotwords(
            "OpenAI, Existing",
            [
                {"original": "openai", "translation": "开放人工智能"},
                {"original": "WhisperX", "translation": "WhisperX"},
            ],
        )

        self.assertEqual(hotwords, "OpenAI, Existing, WhisperX")

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

    def test_format_terms_for_document_prompt_skips_empty_original(self):
        prompt = format_terms_for_document_prompt(
            [
                {"original": "", "translation": "空"},
                {"original": "Term", "translation": ""},
            ]
        )

        self.assertIn("- Term", prompt)
        self.assertNotIn("空", prompt)


if __name__ == "__main__":
    unittest.main()
