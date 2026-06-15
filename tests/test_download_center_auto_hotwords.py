import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.common.config import cfg
from app.core.entities import TranscribeModelEnum
from app.core.utils.transcript_terms import (
    GENERATED_TERMS_BEGIN,
    GENERATED_TERMS_END,
)
from app.view.download_center_interface import DownloadCenterInterface


class _TestableDownloadCenterInterface(DownloadCenterInterface):
    def tr(self, text):
        return text


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _FakeHotwordExtractionThread:
    instances = []

    def __init__(self, file_path, glossary_text, target_language, parent=None):
        self.file_path = file_path
        self.glossary_text = glossary_text
        self.target_language = target_language
        self.parent = parent
        self.started = False
        self.deleted = False
        self.status_changed = _Signal()
        self.succeeded = _Signal()
        self.failed = _Signal()
        self.finished = _Signal()
        self.instances.append(self)

    def start(self):
        self.started = True

    def deleteLater(self):
        self.deleted = True


class DownloadCenterAutoHotwordsTests(unittest.TestCase):
    def setUp(self):
        _FakeHotwordExtractionThread.instances = []
        self.old_model = cfg.transcribe_model.value
        self.old_whisperx_hotwords = cfg.whisperx_hotwords.value
        self.old_mlx_hotwords = cfg.mlx_hotwords.value
        self.old_custom_prompt_text = cfg.custom_prompt_text.value
        self.old_target_language = cfg.target_language.value

    def tearDown(self):
        with patch.object(cfg, "save", return_value=None):
            cfg.set(cfg.transcribe_model, self.old_model)
            cfg.set(cfg.whisperx_hotwords, self.old_whisperx_hotwords)
            cfg.set(cfg.mlx_hotwords, self.old_mlx_hotwords)
            cfg.set(cfg.custom_prompt_text, self.old_custom_prompt_text)
            cfg.set(cfg.target_language, self.old_target_language)

    def _interface(self, transcript_path: Path, work_dir: Path):
        interface = _TestableDownloadCenterInterface.__new__(
            _TestableDownloadCenterInterface
        )
        interface.auto_hotword_extraction_thread = None
        interface.auto_hotword_extraction_target = None
        interface.last_result = {
            "transcript_txt_path": str(transcript_path),
            "work_dir": str(work_dir),
        }
        interface.result_terms_txt = _Label()
        interface.status_label = _Label()
        return interface

    def _patch_ui_side_effects(self):
        infobar = SimpleNamespace(
            success=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
        )
        return patch.multiple(
            "app.view.download_center_interface",
            InfoBar=infobar,
        )

    def test_auto_extraction_starts_with_downloaded_transcript_path(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            cfg, "save", return_value=None
        ), patch(
            "app.components.WhisperXSettingWidget.HotwordExtractionThread",
            _FakeHotwordExtractionThread,
        ):
            transcript_path = Path(temp_dir) / "【视频文稿】Clip.txt"
            transcript_path.write_text("OpenAI and WhisperX", encoding="utf-8")
            interface = self._interface(transcript_path, Path(temp_dir))
            cfg.set(cfg.transcribe_model, TranscribeModelEnum.WHISPER_X)
            cfg.set(cfg.whisperx_hotwords, "Old")
            cfg.set(
                cfg.custom_prompt_text,
                f"keep\n{GENERATED_TERMS_BEGIN}\n- Old -> 旧\n{GENERATED_TERMS_END}",
            )

            interface._maybe_start_auto_hotword_extraction(interface.last_result)

            self.assertEqual(len(_FakeHotwordExtractionThread.instances), 1)
            thread = _FakeHotwordExtractionThread.instances[0]
            self.assertEqual(thread.file_path, str(transcript_path))
            self.assertTrue(thread.started)
            self.assertEqual(cfg.whisperx_hotwords.value, "")
            self.assertEqual(cfg.custom_prompt_text.value, "keep")
            self.assertIn("正在从下载生成的视频文稿提取热词", interface.result_terms_txt.text)

    def test_whisperx_success_overwrites_only_whisperx_hotwords(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            cfg, "save", return_value=None
        ), patch(
            "app.components.WhisperXSettingWidget.HotwordExtractionThread",
            _FakeHotwordExtractionThread,
        ), self._patch_ui_side_effects():
            transcript_path = Path(temp_dir) / "【视频文稿】Clip.txt"
            transcript_path.write_text("OpenAI", encoding="utf-8")
            interface = self._interface(transcript_path, Path(temp_dir))
            cfg.set(cfg.transcribe_model, TranscribeModelEnum.WHISPER_X)
            cfg.set(cfg.whisperx_hotwords, "Old")
            cfg.set(cfg.mlx_hotwords, "MLXOnly")

            interface._start_auto_hotword_extraction(str(transcript_path))
            interface._on_auto_hotwords_extracted(
                [{"original": "OpenAI", "translation": "开放人工智能"}]
            )

            self.assertEqual(cfg.whisperx_hotwords.value, "OpenAI")
            self.assertEqual(cfg.mlx_hotwords.value, "MLXOnly")
            self.assertTrue(Path(interface.last_result["terms_txt_path"]).is_file())
            self.assertIn("【AI术语表】Clip", interface.result_terms_txt.text)

    def test_mlx_success_overwrites_only_mlx_hotwords(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            cfg, "save", return_value=None
        ), patch(
            "app.components.WhisperXSettingWidget.HotwordExtractionThread",
            _FakeHotwordExtractionThread,
        ), self._patch_ui_side_effects():
            transcript_path = Path(temp_dir) / "【视频文稿】Clip.txt"
            transcript_path.write_text("MLX Whisper", encoding="utf-8")
            interface = self._interface(transcript_path, Path(temp_dir))
            cfg.set(cfg.transcribe_model, TranscribeModelEnum.MLX_WHISPER)
            cfg.set(cfg.whisperx_hotwords, "WhisperXOnly")
            cfg.set(cfg.mlx_hotwords, "OldMLX")

            interface._start_auto_hotword_extraction(str(transcript_path))
            interface._on_auto_hotwords_extracted(
                [{"original": "MLX Whisper", "translation": "MLX Whisper"}]
            )

            self.assertEqual(cfg.whisperx_hotwords.value, "WhisperXOnly")
            self.assertEqual(cfg.mlx_hotwords.value, "MLX Whisper")
            self.assertTrue(Path(interface.last_result["terms_txt_path"]).is_file())

    def test_failure_keeps_target_hotwords_empty_and_updates_result_message(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            cfg, "save", return_value=None
        ), patch(
            "app.components.WhisperXSettingWidget.HotwordExtractionThread",
            _FakeHotwordExtractionThread,
        ), self._patch_ui_side_effects():
            transcript_path = Path(temp_dir) / "【视频文稿】Clip.txt"
            transcript_path.write_text("OpenAI", encoding="utf-8")
            interface = self._interface(transcript_path, Path(temp_dir))
            cfg.set(cfg.transcribe_model, TranscribeModelEnum.WHISPER_X)
            cfg.set(cfg.whisperx_hotwords, "Old")

            interface._start_auto_hotword_extraction(str(transcript_path))
            interface._on_auto_hotword_extraction_failed("LLM API 未配置")

            self.assertEqual(cfg.whisperx_hotwords.value, "")
            self.assertIsNone(interface.last_result["terms_txt_path"])
            self.assertIn("自动提取失败：LLM API 未配置", interface.result_terms_txt.text)

    def test_missing_transcript_does_not_start_auto_extraction(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "app.components.WhisperXSettingWidget.HotwordExtractionThread",
            side_effect=AssertionError("should not start"),
        ):
            transcript_path = Path(temp_dir) / "missing.txt"
            interface = self._interface(transcript_path, Path(temp_dir))

            interface._maybe_start_auto_hotword_extraction(interface.last_result)

            self.assertIsNone(interface.auto_hotword_extraction_thread)


if __name__ == "__main__":
    unittest.main()
