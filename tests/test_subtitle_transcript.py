import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.utils.subtitle_transcript import (
    render_transcript_from_subtitle_file,
    write_transcript_txt_file,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class SubtitleTranscriptTests(unittest.TestCase):
    def test_render_youtube_vtt_as_plain_transcript(self):
        self.assertEqual(
            render_transcript_from_subtitle_file(FIXTURES_DIR / "youtube_transcript.vtt"),
            "Hello world.",
        )

    def test_render_srt_as_plain_transcript(self):
        self.assertEqual(
            render_transcript_from_subtitle_file(FIXTURES_DIR / "transcript.srt"),
            "第一句字幕。第二句字幕。",
        )

    def test_adjacent_duplicate_lines_are_removed(self):
        self.assertEqual(
            render_transcript_from_subtitle_file(FIXTURES_DIR / "duplicate_transcript.srt"),
            "Repeat line. Next line.",
        )

    def test_render_json3_as_plain_transcript(self):
        self.assertEqual(
            render_transcript_from_subtitle_file(FIXTURES_DIR / "transcript.json3"),
            "JSON3 line. Next JSON3 line.",
        )

    def test_empty_subtitle_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "没有可生成文稿"):
            render_transcript_from_subtitle_file(FIXTURES_DIR / "empty_transcript.srt")

    def test_write_transcript_txt_file_uses_video_transcript_prefix(self):
        work_dir = Path("download-dir")
        with patch.object(Path, "mkdir") as mocked_mkdir, patch.object(
            Path, "write_text"
        ) as mocked_write_text:
            output_path = Path(
                write_transcript_txt_file(
                    FIXTURES_DIR / "duplicate_transcript.srt", work_dir, "标题"
                )
            )

        self.assertEqual(output_path.parent, work_dir)
        self.assertEqual(output_path.name, "【视频文稿】标题.txt")
        mocked_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mocked_write_text.assert_called_once_with(
            "Repeat line. Next line.",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
