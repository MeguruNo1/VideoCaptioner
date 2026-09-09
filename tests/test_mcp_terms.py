from pathlib import Path

from app.mcp.terms import AUTO_BEGIN, AUTO_END, extract_task_terms, update_glossary_file


def test_extract_task_terms_matches_glossary_and_video_specific_candidates(tmp_path):
    glossary = tmp_path / "terms.md"
    glossary.write_text("# 手工术语\nZenless Zone Zero → 绝区零\nMiyabi → 雅\n", encoding="utf-8")
    result = extract_task_terms(
        "Today Miyabi visits New Eridu. This episode is about Zenless Zone Zero.", glossary
    )
    assert result["glossary"] == {"Zenless Zone Zero": "绝区零", "Miyabi": "雅"}
    assert "New Eridu" in result["candidates"]
    assert "Miyabi" in result["hotwords"]


def test_update_glossary_only_changes_managed_block_and_is_idempotent(tmp_path):
    glossary = tmp_path / "terms.md"
    original = "# 人工维护\nMiyabi → 雅\n"
    glossary.write_text(original, encoding="utf-8")
    assert update_glossary_file(glossary, {"Miyabi": "星见雅", "New Eridu": "新艾利都"}) == [
        ("New Eridu", "新艾利都")
    ]
    updated = glossary.read_text(encoding="utf-8")
    assert updated.startswith(original.rstrip())
    assert AUTO_BEGIN in updated and AUTO_END in updated
    assert "New Eridu → 新艾利都" in updated
    assert update_glossary_file(glossary, {"New Eridu": "新艾利都"}) == []
    assert glossary.read_text(encoding="utf-8") == updated
