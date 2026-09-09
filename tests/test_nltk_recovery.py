import tempfile
import unittest
import hashlib
import io
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import nltk

from app.core.bk_asr.nltk_utils import (
    call_with_punkt_tab_recovery,
    ensure_punkt_tab,
)


class NltkRecoveryTests(unittest.TestCase):
    def test_missing_punkt_tab_is_downloaded_and_retried(self):
        operation = Mock(
            side_effect=[LookupError("Resource 'punkt_tab' not found"), "aligned"]
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            nltk.data, "path", []
        ), patch.object(
            nltk.data,
            "find",
            side_effect=[
                LookupError("missing"),
                LookupError("missing"),
                Path(temp_dir) / "tokenizers" / "punkt_tab",
            ],
        ), patch.object(nltk, "download", return_value=True) as download:
            with patch(
                "app.core.bk_asr.nltk_utils._default_nltk_data_dir",
                return_value=Path(temp_dir),
            ):
                result = call_with_punkt_tab_recovery(operation)

        self.assertEqual(result, "aligned")
        self.assertEqual(operation.call_count, 2)
        download.assert_called_once_with(
            "punkt_tab",
            download_dir=temp_dir,
            quiet=True,
            raise_on_error=True,
        )

    def test_unrelated_lookup_error_is_not_downloaded(self):
        operation = Mock(side_effect=LookupError("another resource is missing"))
        with patch(
            "app.core.bk_asr.nltk_utils.ensure_punkt_tab"
        ) as ensure_resource:
            with self.assertRaisesRegex(LookupError, "another resource"):
                call_with_punkt_tab_recovery(operation)

        ensure_resource.assert_not_called()

    def test_failed_automatic_download_stops_with_clear_error(self):
        operation = Mock(side_effect=LookupError("Resource 'punkt_tab' not found"))
        with patch(
            "app.core.bk_asr.nltk_utils.ensure_punkt_tab",
            side_effect=OSError("network unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "自动下载失败"):
                call_with_punkt_tab_recovery(operation)

        self.assertEqual(operation.call_count, 1)

    def test_existing_resource_does_not_download(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            nltk.data, "path", []
        ), patch.object(
            nltk.data, "find", return_value=Path(temp_dir) / "punkt_tab"
        ), patch.object(nltk, "download") as download:
            result = ensure_punkt_tab(temp_dir)

        self.assertEqual(result, Path(temp_dir))
        download.assert_not_called()

    def test_nltk_security_rejection_uses_verified_official_download(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            nltk.data, "path", []
        ), patch.object(
            nltk.data,
            "find",
            side_effect=[
                LookupError("missing"),
                LookupError("missing"),
                Path(temp_dir) / "tokenizers" / "punkt_tab" / "english",
            ],
        ), patch.object(
            nltk,
            "download",
            side_effect=ValueError("Security Violation [pathsec.urlopen]"),
        ), patch(
            "app.core.bk_asr.nltk_utils._download_official_punkt_tab"
        ) as official_download:
            result = ensure_punkt_tab(temp_dir)

        self.assertEqual(result, Path(temp_dir))
        official_download.assert_called_once_with(Path(temp_dir))

    def test_official_download_rejects_checksum_mismatch(self):
        from app.core.bk_asr import nltk_utils

        response = io.BytesIO(b"not the official archive")
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            nltk_utils.urllib.request, "urlopen", return_value=response
        ):
            with self.assertRaisesRegex(RuntimeError, "校验失败"):
                nltk_utils._download_official_punkt_tab(Path(temp_dir))

    def test_official_download_rejects_unsafe_archive_path(self):
        from app.core.bk_asr import nltk_utils

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("punkt_tab/../../escaped.txt", "unsafe")
        archive_bytes = archive.getvalue()

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            nltk_utils, "_PUNKT_TAB_SHA256", hashlib.sha256(archive_bytes).hexdigest()
        ), patch.object(
            nltk_utils.urllib.request,
            "urlopen",
            return_value=io.BytesIO(archive_bytes),
        ):
            with self.assertRaisesRegex(RuntimeError, "不安全路径"):
                nltk_utils._download_official_punkt_tab(Path(temp_dir))


if __name__ == "__main__":
    unittest.main()
