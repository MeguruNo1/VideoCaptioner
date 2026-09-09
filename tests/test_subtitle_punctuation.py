from app.core.utils.subtitle_punctuation import normalize_cjk_quotes


def test_normalize_curly_and_ascii_quotes_to_corner_brackets():
    assert normalize_cjk_quotes('他说：“Hello”，又说‘你好’。') == "他说：「Hello」，又说『你好』。"
    assert normalize_cjk_quotes('他说 "你好" 和 \'再见\'') == "他说 「你好」 和 『再见』"


def test_normalize_quotes_preserves_word_apostrophes():
    assert normalize_cjk_quotes("don't change O'Reilly") == "don't change O'Reilly"
