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


if __name__ == "__main__":
    unittest.main()
