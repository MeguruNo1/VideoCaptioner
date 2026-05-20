import unittest
from pathlib import Path

from app.core.utils.transcript_file_locator import resolve_default_transcript_path


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "transcript_locator"


class TranscriptFileLocatorTests(unittest.TestCase):
    def test_prefers_explicit_video_transcript_file(self):
        root = FIXTURES_DIR / "video_dir"
        transcript = root / "【视频文稿】标题.txt"

        self.assertEqual(
            resolve_default_transcript_path([root], root),
            str(transcript),
        )

    def test_uses_video_stem_directory_under_work_dir(self):
        root = FIXTURES_DIR / "work_dir"
        video = root / "source" / "Clip.mp4"
        transcript = root / "Clip" / "【视频文稿】Clip.txt"

        self.assertEqual(
            resolve_default_transcript_path([video], root),
            str(transcript),
        )

    def test_falls_back_to_work_dir_when_no_transcript_exists(self):
        root = FIXTURES_DIR / "empty_dir"

        self.assertEqual(resolve_default_transcript_path([], root), str(root))


if __name__ == "__main__":
    unittest.main()
