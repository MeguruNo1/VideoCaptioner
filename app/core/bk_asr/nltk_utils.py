from __future__ import annotations

import logging
import hashlib
import os
import stat
import threading
import urllib.request
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Callable, TypeVar


logger = logging.getLogger(__name__)
_download_lock = threading.Lock()
_Result = TypeVar("_Result")
_PUNKT_TAB_URL = (
    "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/"
    "packages/tokenizers/punkt_tab.zip"
)
_PUNKT_TAB_SHA256 = (
    "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106"
)
_MAX_PUNKT_TAB_ARCHIVE_SIZE = 16 * 1024 * 1024


def _default_nltk_data_dir() -> Path:
    configured = str(os.environ.get("VIDEOCAPTIONER_NLTK_DATA") or "").strip()
    if configured:
        return Path(configured).expanduser()
    try:
        from app.config import APP_DATA_PATH

        return APP_DATA_PATH / "nltk_data"
    except ImportError:
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "VideoCaptioner"
            / "nltk_data"
        )


def _download_official_punkt_tab(target: Path) -> None:
    """Download and safely extract the checksum-pinned official NLTK package."""
    tokenizers_dir = target / "tokenizers"
    tokenizers_dir.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        _PUNKT_TAB_URL,
        headers={"User-Agent": "VideoCaptioner NLTK resource installer"},
    )

    archive_path: Path | None = None
    try:
        digest = hashlib.sha256()
        size = 0
        with NamedTemporaryFile(
            prefix=".punkt_tab-", suffix=".zip", dir=tokenizers_dir, delete=False
        ) as archive:
            archive_path = Path(archive.name)
            with urllib.request.urlopen(request, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > _MAX_PUNKT_TAB_ARCHIVE_SIZE:
                        raise RuntimeError("NLTK punkt_tab 下载文件大小异常")
                    digest.update(chunk)
                    archive.write(chunk)

        if digest.hexdigest() != _PUNKT_TAB_SHA256:
            raise RuntimeError("NLTK punkt_tab 下载文件校验失败")

        with zipfile.ZipFile(archive_path) as package, TemporaryDirectory(
            prefix=".punkt_tab-extract-", dir=tokenizers_dir
        ) as staging_text:
            for member in package.infolist():
                member_path = Path(member.filename)
                member_mode = member.external_attr >> 16
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or not member_path.parts
                    or member_path.parts[0] != "punkt_tab"
                    or stat.S_ISLNK(member_mode)
                ):
                    raise RuntimeError("NLTK punkt_tab 压缩包包含不安全路径")
            package.extractall(staging_text)

            staged_resource = Path(staging_text) / "punkt_tab"
            if not (staged_resource / "english" / "abbrev_types.txt").is_file():
                raise RuntimeError("NLTK punkt_tab 压缩包内容不完整")

            final_resource = tokenizers_dir / "punkt_tab"
            if final_resource.exists():
                raise RuntimeError("NLTK punkt_tab 目标目录存在但资源不完整")
            os.replace(staged_resource, final_resource)
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)


def ensure_punkt_tab(data_dir: str | Path | None = None) -> Path:
    """Make NLTK punkt_tab available, downloading it once when necessary."""
    import nltk

    target = Path(data_dir or _default_nltk_data_dir()).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    target_text = str(target)
    if target_text not in nltk.data.path:
        nltk.data.path.insert(0, target_text)

    try:
        nltk.data.find("tokenizers/punkt_tab")
        return target
    except LookupError:
        pass

    with _download_lock:
        try:
            nltk.data.find("tokenizers/punkt_tab")
            return target
        except LookupError:
            logger.warning("NLTK punkt_tab is missing; downloading to %s", target)

        try:
            downloaded = nltk.download(
                "punkt_tab",
                download_dir=target_text,
                quiet=True,
                raise_on_error=True,
            )
            if not downloaded:
                raise RuntimeError("NLTK Downloader 返回下载失败")
        except Exception as downloader_error:
            logger.warning(
                "NLTK Downloader failed; trying verified official package: %s",
                downloader_error,
            )
            _download_official_punkt_tab(target)
        try:
            nltk.data.find("tokenizers/punkt_tab/english/")
        except LookupError as exc:
            raise RuntimeError("NLTK punkt_tab 下载完成但仍无法读取") from exc
    return target


def call_with_punkt_tab_recovery(operation: Callable[[], _Result]) -> _Result:
    """Retry an NLTK-backed operation once after installing punkt_tab."""
    try:
        return operation()
    except LookupError as exc:
        if "punkt_tab" not in str(exc):
            raise
        try:
            ensure_punkt_tab()
        except Exception as recovery_error:
            raise RuntimeError(
                "WhisperX 对齐缺少 NLTK punkt_tab，自动下载失败；"
                "请检查网络后重新转录"
            ) from recovery_error
        return operation()
