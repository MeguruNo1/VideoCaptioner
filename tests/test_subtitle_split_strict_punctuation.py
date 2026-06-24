import unittest

from app.core.bk_asr.asr_data import ASRDataSeg
from app.core.subtitle_processor.split import (
    SPLIT_STRATEGY_VERSION,
    SubtitleSplitter,
    preprocess_segments,
)


def make_splitter() -> SubtitleSplitter:
    splitter = object.__new__(SubtitleSplitter)
    splitter.max_word_count_cjk = 25
    splitter.max_word_count_english = 20
    splitter.temperature = 0.3
    splitter.model = "test-model"
    splitter.use_cache = False
    splitter.usage_callback = None
    return splitter


class StrictPunctuationSplitTests(unittest.TestCase):
    def test_preprocess_merges_punctuation_token_into_previous_segment(self):
        segments = preprocess_segments(
            [
                ASRDataSeg("那有没有", 0, 300),
                ASRDataSeg("？", 300, 350),
                ASRDataSeg("我来回答", 350, 900),
            ],
            need_lower=False,
        )

        self.assertEqual([seg.text for seg in segments], ["那有没有？", "我来回答"])
        self.assertEqual(segments[0].end_time, 350)

    def test_common_word_split_uses_question_mark_as_hard_boundary(self):
        splitter = make_splitter()
        groups = splitter._split_by_common_words(
            [
                ASRDataSeg("那", 0, 100),
                ASRDataSeg("有没有？", 100, 300),
                ASRDataSeg("我", 300, 400),
                ASRDataSeg("来回答", 400, 700),
            ]
        )

        self.assertEqual(
            [[seg.text for seg in group] for group in groups],
            [["那", "有没有？"], ["我", "来回答"]],
        )

    def test_short_segment_merge_does_not_cross_question_mark(self):
        splitter = make_splitter()
        segments = [
            ASRDataSeg("真的吗？", 0, 200),
            ASRDataSeg("是的", 200, 500),
        ]

        splitter.merge_short_segment(segments)

        self.assertEqual([seg.text for seg in segments], ["真的吗？", "是的"])

    def test_fill_short_display_gap_extends_previous_segment(self):
        segments = [
            ASRDataSeg("第一句", 0, 1000),
            ASRDataSeg("第二句", 1500, 2500),
        ]

        SubtitleSplitter._fill_short_display_gaps(segments)

        self.assertEqual(segments[0].end_time, 1500)
        self.assertEqual(segments[1].start_time, 1500)

    def test_fill_short_display_gap_includes_two_second_boundary(self):
        segments = [
            ASRDataSeg("第一句", 0, 1000),
            ASRDataSeg("第二句", 3000, 4000),
        ]

        SubtitleSplitter._fill_short_display_gaps(segments)

        self.assertEqual(segments[0].end_time, 3000)
        self.assertEqual(segments[1].start_time, 3000)

    def test_fill_short_display_gap_keeps_large_pause(self):
        segments = [
            ASRDataSeg("第一句", 0, 1000),
            ASRDataSeg("第二句", 3001, 4000),
        ]

        SubtitleSplitter._fill_short_display_gaps(segments)

        self.assertEqual(segments[0].end_time, 1000)
        self.assertEqual(segments[1].start_time, 3001)

    def test_fill_short_display_gap_ignores_zero_and_overlap(self):
        zero_gap_segments = [
            ASRDataSeg("第一句", 0, 1000),
            ASRDataSeg("第二句", 1000, 2000),
        ]
        overlap_segments = [
            ASRDataSeg("第一句", 0, 1200),
            ASRDataSeg("第二句", 1000, 2000),
        ]

        SubtitleSplitter._fill_short_display_gaps(zero_gap_segments)
        SubtitleSplitter._fill_short_display_gaps(overlap_segments)

        self.assertEqual(zero_gap_segments[0].end_time, 1000)
        self.assertEqual(overlap_segments[0].end_time, 1200)

    def test_llm_restored_question_mark_splits_original_timeline(self):
        splitter = make_splitter()
        result = splitter._split_long_segment(
            [
                ASRDataSeg("你", 0, 100),
                ASRDataSeg("好吗", 100, 300),
                ASRDataSeg("我", 300, 400),
                ASRDataSeg("很好", 400, 700),
            ],
            hint_text="你好吗？我很好。",
        )

        self.assertEqual([seg.text for seg in result], ["你好吗", "我很好"])

    def test_llm_hint_boundaries_are_not_reused_after_first_split(self):
        splitter = make_splitter()
        result = splitter._split_long_segment(
            [
                ASRDataSeg("你", 0, 100),
                ASRDataSeg("好吗", 100, 300),
                ASRDataSeg("我", 300, 400),
                ASRDataSeg("很好", 400, 700),
                ASRDataSeg("谢谢", 700, 900),
            ],
            hint_text="你好吗？我很好谢谢。",
        )

        self.assertEqual([seg.text for seg in result], ["你好吗", "我很好谢谢"])

    def test_split_cache_key_includes_strategy_version(self):
        class FakeCache:
            def __init__(self):
                self.params = None

            def get_llm_result(self, prompt, model_name, **params):
                self.params = params
                return '["cached"]'

        splitter = make_splitter()
        splitter.use_cache = True
        splitter.cache_manager = FakeCache()

        result = splitter._call_split_llm(
            stage="split",
            cache_key="source",
            source_text="source",
            system_prompt="system",
            user_prompt="user",
        )

        self.assertEqual(result, ["cached"])
        self.assertEqual(
            splitter.cache_manager.params["split_strategy_version"],
            SPLIT_STRATEGY_VERSION,
        )

    def test_fuzzy_alignment_preserves_words_before_best_match(self):
        splitter = make_splitter()
        source = [
            ASRDataSeg("What", 0, 100),
            ASRDataSeg("we're", 100, 200),
            ASRDataSeg("really", 200, 300),
            ASRDataSeg("here", 300, 400),
            ASRDataSeg("to", 400, 500),
            ASRDataSeg("talk", 500, 600),
        ]

        result = splitter._merge_segments_based_on_sentences(
            source, ["Here to talk."]
        )

        self.assertEqual(
            splitter._lexical_tokens(result),
            ["what", "we're", "really", "here", "to", "talk"],
        )

    def test_alignment_preserves_unmatched_trailing_words(self):
        splitter = make_splitter()
        source = [
            ASRDataSeg("one", 0, 100),
            ASRDataSeg("two", 100, 200),
            ASRDataSeg("three", 200, 300),
            ASRDataSeg("four", 300, 400),
        ]

        result = splitter._merge_segments_based_on_sentences(source, ["one two"])

        self.assertEqual(
            splitter._lexical_tokens(result),
            ["one", "two", "three", "four"],
        )

    def test_lexical_coverage_detects_dropped_words(self):
        splitter = make_splitter()
        source = [ASRDataSeg("I", 0, 100), ASRDataSeg("do", 100, 200)]
        incomplete = [ASRDataSeg("do", 100, 200)]

        self.assertFalse(splitter._has_same_lexical_content(source, incomplete))


if __name__ == "__main__":
    unittest.main()
