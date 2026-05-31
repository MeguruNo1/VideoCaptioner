import unittest

from app.core.bk_asr.mlx_workflow import (
    build_chunk_windows,
    merge_transcription_results,
    offset_transcription_result,
)


class MLXWhisperWorkflowTests(unittest.TestCase):
    def test_builds_overlapping_chunk_windows_with_keep_ranges(self):
        windows = build_chunk_windows(
            duration_seconds=1250,
            chunk_duration_seconds=600,
            overlap_seconds=30,
        )

        self.assertEqual(
            windows,
            [
                (0.0, 600.0, 0.0, 585.0),
                (570.0, 1170.0, 585.0, 1155.0),
                (1140.0, 1250.0, 1155.0, 1250.0),
            ],
        )

    def test_offsets_result_to_global_timestamps_and_filters_overlap(self):
        result = offset_transcription_result(
            {
                "segments": [
                    {
                        "start": 0.1,
                        "end": 5.0,
                        "text": "early",
                        "words": [{"word": "early", "start": 0.1, "end": 0.4}],
                    },
                    {
                        "start": 31.0,
                        "end": 33.0,
                        "text": "kept",
                        "words": [{"word": "kept", "start": 31.0, "end": 33.0}],
                    },
                ]
            },
            offset_seconds=570.0,
            keep_start_seconds=585.0,
            keep_end_seconds=1155.0,
        )

        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(result["segments"][0]["text"], "kept")
        self.assertEqual(result["segments"][0]["start"], 601.0)
        self.assertEqual(result["segments"][0]["words"][0]["start"], 601.0)

    def test_offsets_result_filters_words_without_dropping_boundary_segment(self):
        result = offset_transcription_result(
            {
                "segments": [
                    {
                        "start": 10.0,
                        "end": 40.0,
                        "text": "drop keep",
                        "words": [
                            {"word": "drop", "start": 10.0, "end": 10.4},
                            {"word": "keep", "start": 31.0, "end": 31.5},
                        ],
                    },
                ]
            },
            offset_seconds=570.0,
            keep_start_seconds=600.0,
            keep_end_seconds=650.0,
        )

        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(result["segments"][0]["text"], "keep")
        self.assertEqual(result["segments"][0]["start"], 601.0)
        self.assertEqual(result["segments"][0]["end"], 601.5)

    def test_merges_results_and_dedupes_overlap_words(self):
        merged = merge_transcription_results(
            [
                {
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "hello",
                            "words": [{"word": "hello", "start": 0.0, "end": 1.0}],
                        }
                    ]
                },
                {
                    "segments": [
                        {
                            "start": 0.05,
                            "end": 1.05,
                            "text": "hello",
                            "words": [{"word": "hello", "start": 0.05, "end": 1.05}],
                        },
                        {
                            "start": 1.2,
                            "end": 2.0,
                            "text": "world",
                            "words": [{"word": "world", "start": 1.2, "end": 2.0}],
                        },
                    ]
                },
            ]
        )

        self.assertEqual([word["word"] for word in merged["segments"][0]["words"]], ["hello"])
        self.assertEqual([word["word"] for word in merged["segments"][1]["words"]], ["world"])
