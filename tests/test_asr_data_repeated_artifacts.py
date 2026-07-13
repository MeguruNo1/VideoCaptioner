from app.core.bk_asr.asr_data import ASRData, ASRDataSeg


def _seg(text: str, index: int) -> ASRDataSeg:
    return ASRDataSeg(text, index * 100, index * 100 + 50)


def test_collapses_long_duplicate_word_runs():
    asr_data = ASRData(
        [_seg("Select", 0), _seg("our", 1)]
        + [_seg("library", index) for index in range(2, 222)]
        + [_seg("Thank", 223), _seg("you", 224)]
    )

    asr_data.remove_repeated_asr_artifacts()

    assert [seg.text for seg in asr_data.segments] == [
        "Select",
        "our",
        "library",
        "Thank",
        "you",
    ]


def test_collapses_repeated_phrase_loops_but_keeps_short_repetitions():
    asr_data = ASRData(
        [_seg("very", 0), _seg("very", 1)]
        + [
            _seg(text, index + 2)
            for index, text in enumerate(
                [
                    "Select",
                    "our",
                    "library",
                    "Select",
                    "our",
                    "library",
                    "Select",
                    "our",
                    "library",
                    "Select",
                    "our",
                    "library",
                    "next",
                ]
            )
        ]
    )

    asr_data.remove_repeated_asr_artifacts()

    assert [seg.text for seg in asr_data.segments] == [
        "very",
        "very",
        "Select",
        "our",
        "library",
        "next",
    ]


def test_collapses_repeated_phrase_loops_with_punctuation_separators():
    asr_data = ASRData(
        [_seg("before", 0)]
        + [
            _seg(text, index + 1)
            for index, text in enumerate(["5", "-"] * 120 + ["5"])
        ]
        + [_seg("after", 242)]
    )

    asr_data.remove_repeated_asr_artifacts()

    assert [seg.text for seg in asr_data.segments] == [
        "before",
        "5",
        "-",
        "after",
    ]


def test_removes_only_fullwidth_periods_from_translated_text():
    asr_data = ASRData(
        [
            ASRDataSeg(
                "原文。",
                0,
                100,
                translated_text="中文。English. 3.14。",
            )
        ]
    )

    asr_data.remove_translated_periods()

    assert asr_data.segments[0].translated_text == "中文English. 3.14"
