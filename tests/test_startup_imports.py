import json
import subprocess
import sys
import textwrap
import unittest


class StartupImportTests(unittest.TestCase):
    def test_main_import_does_not_load_task_backends(self):
        code = textwrap.dedent(
            """
            import json
            import sys

            import main  # noqa: F401

            watched = [
                "torch",
                "torchaudio",
                "whisperx",
                "mlx_whisper",
                "yt_dlp",
                "openai",
                "app.core.bk_asr.transcribe",
                "app.core.bk_asr.mlx_whisper",
                "app.core.bk_asr.whisper_x_auto",
                "app.thread.transcript_thread_clean",
                "app.thread.subtitle_thread",
                "app.thread.video_download_thread",
                "app.core.subtitle_processor.split",
                "app.core.subtitle_processor.optimize",
                "app.core.subtitle_processor.translate",
                "app.core.utils.video_utils",
                "app.core.utils.subtitle_preview",
            ]
            print(
                json.dumps(
                    {name: name in sys.modules for name in watched},
                    sort_keys=True,
                )
            )
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
        )
        loaded = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(
            {name: False for name in loaded},
            loaded,
        )


if __name__ == "__main__":
    unittest.main()
