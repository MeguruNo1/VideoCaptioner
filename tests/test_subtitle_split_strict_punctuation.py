import unittest

from app.core.bk_asr.asr_data import ASRData, ASRDataSeg
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
    splitter.timeout = 30
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

    def test_title_abbreviation_period_is_not_a_strong_boundary(self):
        splitter = make_splitter()
        segments = [
            ASRDataSeg("Please", 0, 100),
            ASRDataSeg("welcome", 100, 200),
            ASRDataSeg("Mr.", 200, 300),
            ASRDataSeg("Smith", 300, 400),
            ASRDataSeg("today.", 400, 500),
        ]

        groups = splitter._split_by_strong_terminal_punctuation(segments)

        self.assertFalse(splitter._has_strong_terminal_boundary("Mr.", "Smith"))
        self.assertFalse(splitter._has_strong_terminal_boundary("Mrs.", "Jones"))
        self.assertTrue(splitter._has_strong_terminal_boundary("Mr."))
        self.assertTrue(splitter._has_strong_terminal_boundary("today."))
        for title, surname in (("Mr.", "He"), ("Mrs.", "May"), ("Mr.", "Will")):
            with self.subTest(title=title, surname=surname):
                self.assertFalse(
                    splitter._has_strong_terminal_boundary(title, surname)
                )
        self.assertEqual(
            [[seg.text for seg in group] for group in groups],
            [["Please", "welcome", "Mr.", "Smith", "today."]],
        )

    def test_hint_boundaries_ignore_title_abbreviation_periods(self):
        splitter = make_splitter()
        hint = "Please welcome Mr. Smith today. Mrs. Jones speaks."

        self.assertEqual(
            splitter._hint_terminal_boundary_counts(hint, is_cjk_text=False),
            {5, 8},
        )
        self.assertEqual(
            splitter._hint_boundary_counts(hint, is_cjk_text=False),
            {5, 8},
        )

        real_sentence_end = "The abbreviation is Mr."
        self.assertEqual(
            splitter._hint_terminal_boundary_counts(
                real_sentence_end, is_cjk_text=False
            ),
            {4},
        )

    def test_cjk_hint_scanning_ignores_embedded_title_abbreviation_period(self):
        splitter = make_splitter()
        hint = "欢迎Mr. Smith。"

        self.assertEqual(
            splitter._hint_terminal_boundary_counts(hint, is_cjk_text=True),
            {9},
        )
        self.assertEqual(
            splitter._hint_boundary_counts(hint, is_cjk_text=True),
            {9},
        )

    def test_split_stage_cannot_add_title_name_boundary(self):
        splitter = make_splitter()
        splitter.split_type = "sentence"
        splitter._call_split_llm = lambda **_: [
            "Please welcome Mr.",
            "Smith today.",
        ]

        self.assertEqual(
            splitter._split_restored_sentences_with_llm(
                "Please welcome Mr Smith today",
                ["Please welcome Mr. Smith today."],
            ),
            ["Please welcome Mr. Smith today."],
        )

    def test_split_stage_preserves_restored_sentence_boundary_after_title(self):
        self.assertEqual(
            SubtitleSplitter._merge_title_boundaries_added_by_split_stage(
                ["The abbreviation is Mr.", "Are you familiar with it?"],
                ["The abbreviation is Mr.", "Are you familiar with it?"],
            ),
            ["The abbreviation is Mr.", "Are you familiar with it?"],
        )

    def test_long_split_keeps_titles_with_names_and_honors_real_periods(self):
        splitter = make_splitter()
        result = splitter._split_long_segment(
            [
                ASRDataSeg("Please", 0, 100),
                ASRDataSeg("welcome", 100, 200),
                ASRDataSeg("Mr.", 200, 300),
                ASRDataSeg("Smith.", 300, 400),
                ASRDataSeg("Mrs.", 400, 500),
                ASRDataSeg("Jones", 500, 600),
                ASRDataSeg("arrived.", 600, 700),
            ]
        )

        self.assertEqual(
            [seg.text for seg in result],
            ["Please welcome Mr. Smith.", "Mrs. Jones arrived."],
        )

    def test_restored_hint_keeps_titles_with_names(self):
        splitter = make_splitter()
        result = splitter._split_long_segment(
            [
                ASRDataSeg("Please", 0, 100),
                ASRDataSeg("welcome", 100, 200),
                ASRDataSeg("Mr", 200, 300),
                ASRDataSeg("Smith", 300, 400),
                ASRDataSeg("Mrs", 400, 500),
                ASRDataSeg("Jones", 500, 600),
                ASRDataSeg("arrived", 600, 700),
            ],
            hint_text="Please welcome Mr. Smith. Mrs. Jones arrived.",
        )

        self.assertEqual(
            [seg.text for seg in result],
            ["Please welcome Mr Smith", "Mrs Jones arrived"],
        )

    def test_common_word_split_does_not_use_title_period_as_suffix(self):
        splitter = make_splitter()
        splitter.max_word_count_english = 5

        for title, name in (("Mr.", "Smith"), ("Mrs.", "Jones")):
            with self.subTest(title=title):
                groups = splitter._split_by_common_words(
                    [
                        ASRDataSeg("Please", 0, 100),
                        ASRDataSeg("welcome", 100, 200),
                        ASRDataSeg(title, 200, 300),
                        ASRDataSeg(name, 300, 400),
                        ASRDataSeg("today", 400, 500),
                    ]
                )

                self.assertEqual(len(groups), 1)

    def test_length_split_does_not_end_a_segment_with_title(self):
        splitter = make_splitter()
        splitter.max_word_count_english = 6

        for title in ("Mr.", "Mrs."):
            with self.subTest(title=title):
                result = splitter._split_long_segment(
                    [
                        ASRDataSeg("one", 0, 100),
                        ASRDataSeg("two", 100, 200),
                        ASRDataSeg("three", 200, 300),
                        ASRDataSeg("four", 300, 400),
                        ASRDataSeg(title, 400, 500),
                        ASRDataSeg("Smith", 500, 600),
                        ASRDataSeg("seven", 600, 700),
                        ASRDataSeg("eight", 700, 800),
                    ]
                )

                self.assertEqual(
                    [seg.text for seg in result],
                    [f"one two three four {title} Smith", "seven eight"],
                )

    def test_unpunctuated_source_uses_restored_title_hint_without_splitting(self):
        splitter = make_splitter()
        splitter.max_word_count_english = 6
        words = ["one", "two", "three", "four", "Mr", "Smith", "seven", "eight"]
        segments = [
            ASRDataSeg(word, index * 100, (index + 1) * 100)
            for index, word in enumerate(words)
        ]

        result = splitter._split_long_segment(
            segments,
            hint_text="one two three four Mr. Smith seven eight",
        )

        self.assertEqual(
            [seg.text for seg in result],
            ["one two three four Mr Smith", "seven eight"],
        )

    def test_short_title_segment_merges_with_name(self):
        splitter = make_splitter()

        for title, name in (("Mr.", "Smith"), ("Mrs.", "Jones")):
            with self.subTest(title=title):
                segments = [
                    ASRDataSeg(title, 0, 100),
                    ASRDataSeg(name, 100, 200),
                ]

                splitter.merge_short_segment(segments)

                self.assertEqual([seg.text for seg in segments], [f"{title} {name}"])

    def test_large_input_chunking_does_not_split_title_from_name(self):
        splitter = make_splitter()
        words = ["word"] * 600
        words[300:302] = ["Mr", "Smith"]
        segments = []
        current_time = 0
        for index, word in enumerate(words):
            segments.append(ASRDataSeg(word, current_time, current_time + 50))
            current_time += 1050 if index == 300 else 100

        parts = splitter._split_asr_data(ASRData(segments), num_segments=2)

        self.assertEqual(sum(len(part.segments) for part in parts), 600)
        title_part = next(part for part in parts if "Mr" in part.to_txt())
        title_index = [seg.text for seg in title_part.segments].index("Mr")
        self.assertEqual(title_part.segments[title_index + 1].text, "Smith")

    def test_time_gap_grouping_keeps_title_with_name(self):
        splitter = make_splitter()
        segments = [
            ASRDataSeg(f"word{index}", index * 100, index * 100 + 50)
            for index in range(17)
        ]
        segments.extend(
            [
                ASRDataSeg("Mr", 1700, 1750),
                ASRDataSeg("Smith", 3750, 3800),
                ASRDataSeg("arrived", 3800, 3900),
            ]
        )

        rule_groups = splitter._group_by_time_gaps(
            segments, max_gap=500, check_large_gaps=True
        )
        alignment_groups = splitter._group_by_time_gaps(segments, max_gap=1500)

        self.assertEqual(len(rule_groups), 1)
        self.assertEqual(len(alignment_groups), 1)

    def test_rule_fallback_does_not_preserve_a_gap_split_after_title(self):
        splitter = make_splitter()
        words = [f"word{index}" for index in range(28)]
        words[16:18] = ["Mr", "Smith"]
        segments = []
        current_time = 0
        for index, word in enumerate(words):
            segments.append(ASRDataSeg(word, current_time, current_time + 50))
            current_time += 1050 if index == 16 else 100

        result = splitter._process_by_rules(segments)

        self.assertTrue(all(not seg.text.endswith("Mr") for seg in result))

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

    def test_fill_short_display_gap_keeps_gap_above_half_second(self):
        segments = [
            ASRDataSeg("第一句", 0, 1000),
            ASRDataSeg("第二句", 1501, 2500),
        ]

        SubtitleSplitter._fill_short_display_gaps(segments)

        self.assertEqual(segments[0].end_time, 1000)
        self.assertEqual(segments[1].start_time, 1501)

    def test_fill_short_display_gap_keeps_large_pause(self):
        segments = [
            ASRDataSeg("第一句", 0, 1000),
            ASRDataSeg("第二句", 3000, 4000),
        ]

        SubtitleSplitter._fill_short_display_gaps(segments)

        self.assertEqual(segments[0].end_time, 1000)
        self.assertEqual(segments[1].start_time, 3000)

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

    def test_rejects_exploded_split_result(self):
        class FakeMessage:
            content = "<br>".join(["library"] * 250)

        class FakeChoice:
            message = FakeMessage()

        class FakeCompletions:
            @staticmethod
            def create(**_):
                return type("Response", (), {"choices": [FakeChoice()]})()

        class FakeClient:
            chat = type(
                "Chat",
                (),
                {"completions": FakeCompletions()},
            )()

        splitter = make_splitter()
        splitter.client = FakeClient()

        with self.assertRaisesRegex(ValueError, "结果异常过多"):
            splitter._call_split_llm(
                stage="split",
                cache_key="source",
                source_text=" ".join(["library"] * 20),
                system_prompt="system",
                user_prompt="user",
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
