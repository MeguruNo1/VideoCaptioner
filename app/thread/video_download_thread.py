import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

import requests
import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal

from app.config import APP_DATA_PATH
from app.core.utils.logger import setup_logger
from app.core.utils.download_description import write_description_txt_file
from app.core.utils.subtitle_transcript import write_transcript_txt_file
from app.core.utils.proxy_utils import (
    apply_download_proxy_environment,
    get_effective_download_proxy_url,
)
from app.core.utils.macos_video_transcoder import (
    get_native_video_codec,
    is_native_hevc_transcode_supported,
    transcode_video_to_hevc_native,
)

logger = setup_logger("video_download_thread")

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".flv",
    ".m4v",
}
AUDIO_EXTENSIONS = {
    ".m4a",
    ".mp3",
    ".aac",
    ".wav",
    ".flac",
    ".opus",
    ".ogg",
    ".weba",
    ".webm",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SUBTITLE_EXTENSIONS = {
    ".srt",
    ".vtt",
    ".lrc",
    ".json3",
    ".srv1",
    ".srv2",
    ".srv3",
}
NO_COOKIE_FILE_PATH = APP_DATA_PATH / "__no_cookie__.txt"


class DownloadCancelledError(Exception):
    """Raised when the user explicitly terminates an in-flight download."""


def sanitize_filename(name: str, replacement: str = "_") -> str:
    forbidden_chars = r'<>:"/\\|?*'
    sanitized = re.sub(f"[{re.escape(forbidden_chars)}]", replacement, name)
    sanitized = re.sub(r"[\0-\31]", "", sanitized)
    sanitized = sanitized.rstrip(" .")

    max_length = 255
    if len(sanitized) > max_length:
        base, ext = os.path.splitext(sanitized)
        base_max_length = max_length - len(ext)
        sanitized = base[:base_max_length] + ext

    return sanitized or "default_filename"


def _requests_kwargs(proxy_url: str) -> dict:
    if not proxy_url:
        return {}
    return {"proxies": {"http": proxy_url, "https": proxy_url}}


def _safe_size(value) -> int | None:
    if value in (None, "", 0):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_bytes(size: int | None) -> str:
    if not size:
        return "未知大小"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{value:.1f}{units[unit_index]}"


def _format_duration(seconds) -> str:
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return "未知时长"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_number(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "未知"


def _friendly_codec(codec: str | None) -> str:
    if not codec or codec == "none":
        return ""
    return str(codec).replace(".", " ").upper()


def _format_resolution(item: dict) -> str:
    if item.get("height"):
        return f"{item['height']}p"
    if item.get("width"):
        return f"{item['width']}w"
    return item.get("resolution") or "未知"


def _extract_language(item: dict) -> str:
    language = item.get("language") or item.get("language_preference")
    if language in (None, "", -1):
        return ""
    return str(language).upper()


def _build_format_entry(item: dict) -> dict | None:
    vcodec = item.get("vcodec")
    acodec = item.get("acodec")
    has_video = bool(vcodec and vcodec != "none")
    has_audio = bool(acodec and acodec != "none")
    if not has_video and not has_audio:
        return None

    filesize = _safe_size(item.get("filesize")) or _safe_size(item.get("filesize_approx"))
    fps = item.get("fps")
    abr = item.get("abr") or item.get("tbr")
    ext = item.get("ext") or ""
    dynamic_range = item.get("dynamic_range") or ""

    detail_parts = []
    language = _extract_language(item)
    if language:
        detail_parts.append(language)
    if fps:
        detail_parts.append(f"{int(fps)}FPS")
    if dynamic_range and str(dynamic_range).upper() not in {"SDR", "UNKNOWN"}:
        detail_parts.append(str(dynamic_range).upper())
    if has_video and _friendly_codec(vcodec):
        detail_parts.append(_friendly_codec(vcodec))
    if has_audio and not has_video and _friendly_codec(acodec):
        detail_parts.append(_friendly_codec(acodec))
    if has_video and has_audio:
        detail_parts.append("含音频")
    if ext:
        detail_parts.append(ext)
    detail_parts.append(_format_bytes(filesize))

    quality = _format_resolution(item) if has_video else f"{int(abr)}kbps" if abr else "音频"

    return {
        "format_id": str(item.get("format_id", "")),
        "ext": ext,
        "quality": quality,
        "details": " · ".join(part for part in detail_parts if part),
        "filesize": filesize,
        "fps": fps or 0,
        "height": item.get("height") or 0,
        "width": item.get("width") or 0,
        "abr": abr or 0,
        "language": language,
        "vcodec": vcodec or "",
        "acodec": acodec or "",
        "dynamic_range": dynamic_range or "",
        "has_video": has_video,
        "has_audio": has_audio,
        "channels": item.get("audio_channels") or item.get("channels") or 0,
        "protocol": item.get("protocol") or "",
    }


def normalize_preview_data(url: str, info_dict: dict, thumbnail_bytes: bytes | None = None) -> dict:
    video_formats = []
    audio_formats = []
    for item in info_dict.get("formats") or []:
        entry = _build_format_entry(item)
        if not entry:
            continue
        if entry["has_video"]:
            video_formats.append(entry)
        elif entry["has_audio"]:
            audio_formats.append(entry)

    video_formats.sort(
        key=lambda item: (item.get("height", 0), item.get("fps", 0), item.get("filesize", 0) or 0),
        reverse=True,
    )
    audio_formats.sort(
        key=lambda item: (item.get("abr", 0), item.get("filesize", 0) or 0, item.get("channels", 0)),
        reverse=True,
    )

    subtitles = info_dict.get("subtitles") or {}
    automatic_captions = info_dict.get("automatic_captions") or {}
    return {
        "url": url,
        "title": info_dict.get("title") or "未命名视频",
        "uploader": info_dict.get("uploader") or info_dict.get("channel") or "未知作者",
        "duration_text": _format_duration(info_dict.get("duration")),
        "upload_date": info_dict.get("upload_date") or "",
        "view_count_text": _format_number(info_dict.get("view_count")),
        "thumbnail_url": info_dict.get("thumbnail") or "",
        "thumbnail_bytes": thumbnail_bytes,
        "video_formats": video_formats,
        "audio_formats": audio_formats,
        "manual_subtitle_languages": sorted(subtitles.keys()),
        "auto_subtitle_languages": sorted(automatic_captions.keys()),
        "has_manual_subtitles": bool(subtitles),
        "has_auto_subtitles": bool(automatic_captions),
        "info_dict": info_dict,
    }


def _pick_subtitle_item(
    info_dict: dict, subtitle_mode: str, subtitle_language: str | None
) -> tuple[str | None, str]:
    sources = (
        info_dict.get("subtitles", {})
        if subtitle_mode == "manual"
        else info_dict.get("automatic_captions", {})
    )
    if not sources:
        return None, "vtt"

    preferred_keys = []
    if subtitle_language:
        preferred_keys.append(subtitle_language)
        preferred_keys.extend(
            [key for key in sources.keys() if key.startswith(subtitle_language)]
        )

    candidate_keys = preferred_keys + list(sources.keys())
    seen = set()
    for key in candidate_keys:
        if key in seen or key not in sources:
            continue
        seen.add(key)
        entries = sources.get(key) or []
        if not entries:
            continue
        item = entries[-1]
        url = item.get("url")
        ext = item.get("ext") or "vtt"
        if url:
            return url, ext

    return None, "vtt"


def _download_subtitle_fallback(
    subtitle_download_link: str | None,
    subtitle_ext: str,
    subtitle_path: Path,
    proxy_url: str,
) -> str | None:
    if not subtitle_download_link:
        return None
    response = requests.get(
        subtitle_download_link, timeout=30, **_requests_kwargs(proxy_url)
    )
    response.raise_for_status()
    subtitle_path = subtitle_path.with_suffix(f".{subtitle_ext or 'vtt'}")
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    with open(subtitle_path, "w", encoding="utf-8") as file:
        file.write(response.text)
    return str(subtitle_path)


def _download_thumbnail_fallback(
    thumbnail_url: str | None, thumbnail_path: Path, proxy_url: str
) -> str | None:
    if not thumbnail_url:
        return None
    response = requests.get(thumbnail_url, timeout=30, **_requests_kwargs(proxy_url))
    response.raise_for_status()
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    with open(thumbnail_path, "wb") as file:
        file.write(response.content)
    return str(thumbnail_path)


def _normalize_thumbnail_to_png(thumbnail_path: str | Path | None) -> str | None:
    if not thumbnail_path:
        return None

    path = Path(thumbnail_path)
    if not path.exists():
        return None

    png_path = path.with_suffix(".png")
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.save(png_path, format="PNG")
        if path.resolve() != png_path.resolve() and path.exists():
            path.unlink()
        return str(png_path)
    except Exception as exc:
        logger.warning("封面转换 PNG 失败，保留原文件: %s", exc)
        return str(path)


def _resolve_download_engine_strategy(
    strategy: str | None, proxy_url: str, cookiefile_path: Path
) -> str | None:
    if strategy not in {"单线程", "多线程", "智能选择"}:
        return None
    if strategy != "智能选择":
        return strategy
    if proxy_url or cookiefile_path.exists():
        return "单线程"
    return "多线程"


def _build_strategy_options(strategy: str | None) -> dict:
    if strategy == "单线程":
        return {
            "concurrent_fragment_downloads": 1,
            "retries": 10,
            "fragment_retries": 10,
        }
    if strategy == "多线程":
        return {
            "concurrent_fragment_downloads": 4,
            "retries": 3,
            "fragment_retries": 3,
        }
    return {}


def _build_youtube_challenge_options() -> dict:
    node_path = shutil.which("node")
    if not node_path:
        for candidate in ("/usr/local/bin/node", "/opt/homebrew/bin/node"):
            if Path(candidate).is_file():
                node_path = candidate
                break
    if not node_path:
        return {}
    return {
        "js_runtimes": {
            "node": {
                "path": node_path,
            }
        },
        "remote_components": {"ejs:github"},
    }


def _robust_format_selector(selector: str, download_mode: str = "video_audio") -> str:
    selector = str(selector or "").strip()
    if not selector:
        if download_mode == "audio":
            return "bestaudio/best"
        if download_mode == "video":
            return "bv*/bestvideo/best"
        return "bv*+ba/bestvideo+bestaudio/best"

    if "bv*+ba" in selector:
        return selector

    replacements = {
        "bestvideo+bestaudio/best": "bv*+ba/bestvideo+bestaudio/best",
        "bestvideo/best": "bv*/bestvideo/best",
    }
    if selector in replacements:
        return replacements[selector]

    if download_mode == "video_audio" and "bestvideo+bestaudio/best" in selector:
        return selector.replace(
            "bestvideo+bestaudio/best",
            "bv*+ba/bestvideo+bestaudio/best",
        )
    return selector


def _build_ydl_options(proxy_url: str, cookiefile_path: Path, progress_hooks=None) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
        "nocheckcertificate": False,
    }
    if progress_hooks:
        options["progress_hooks"] = progress_hooks
    if proxy_url:
        options["proxy"] = proxy_url
    if cookiefile_path.exists():
        logger.info("使用 cookiefile: %s", cookiefile_path)
        options["cookiefile"] = str(cookiefile_path)
    else:
        options["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "ios", "tv"],
            }
        }
    options.update(_build_youtube_challenge_options())
    return options


def _has_downloadable_media_formats(info_dict: dict) -> bool:
    for item in info_dict.get("formats") or []:
        vcodec = item.get("vcodec")
        acodec = item.get("acodec")
        if (vcodec and vcodec != "none") or (acodec and acodec != "none"):
            return True
    return False


def _extract_metadata_info(
    url: str,
    proxy_url: str,
    cookiefile_path: Path,
    effective_strategy: str | None,
) -> dict:
    def extract_once(active_cookiefile_path: Path) -> dict:
        options = _build_ydl_options(proxy_url, active_cookiefile_path)
        options.update(_build_strategy_options(effective_strategy))
        options.update(
            {
                "skip_download": True,
                "extract_flat": False,
                "lazy_playlist": False,
            }
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False, process=False)

    info_dict = extract_once(cookiefile_path)

    if not isinstance(info_dict, dict) or not info_dict.get("formats"):
        raise RuntimeError("无法解析可用格式列表")

    if cookiefile_path.exists() and not _has_downloadable_media_formats(info_dict):
        logger.warning("使用 cookies 仅解析到图片格式，改为不带 cookies 重试")
        fallback_info_dict = extract_once(NO_COOKIE_FILE_PATH)
        if isinstance(fallback_info_dict, dict) and _has_downloadable_media_formats(fallback_info_dict):
            fallback_info_dict["_videocaptioner_disable_cookiefile"] = True
            return fallback_info_dict

    return info_dict


def _time_text_to_seconds(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) not in {2, 3} or not all(part.isdigit() for part in parts):
        return None
    try:
        if len(parts) == 2:
            minutes, seconds = map(int, parts)
            hours = 0
        else:
            hours, minutes, seconds = map(int, parts)
    except ValueError:
        return None
    if minutes < 0 or seconds < 0 or seconds >= 60 or (len(parts) == 3 and minutes >= 60):
        return None
    return hours * 3600 + minutes * 60 + seconds


def _parse_download_section(section: str) -> dict | None:
    value = str(section or "").strip()
    if not value.startswith("*") or "-" not in value:
        return None
    time_range = value[1:]
    start_text, end_text = time_range.split("-", 1)
    start_seconds = _time_text_to_seconds(start_text)
    end_seconds = _time_text_to_seconds(end_text)
    if start_seconds is None or end_seconds is None or start_seconds >= end_seconds:
        return None
    return {
        "start_time": start_seconds,
        "end_time": end_seconds,
    }


def _build_download_ranges_callback(download_sections: list[str]):
    parsed_sections = []
    for index, section in enumerate(download_sections or [], start=1):
        parsed = _parse_download_section(section)
        if not parsed:
            raise RuntimeError(f"无效的时间段配置: {section}")
        parsed["title"] = f"section_{index:02d}"
        parsed["index"] = index
        parsed_sections.append(parsed)

    def _callback(_info_dict, _ydl):
        return parsed_sections or [{}]

    return _callback


def extract_preview(url: str, download_engine_strategy: str | None = None) -> dict:
    proxy_url = apply_download_proxy_environment()
    cookiefile_path = APP_DATA_PATH / "cookies.txt"
    effective_strategy = _resolve_download_engine_strategy(
        download_engine_strategy, proxy_url, cookiefile_path
    )
    info_dict = _extract_metadata_info(
        url, proxy_url, cookiefile_path, effective_strategy
    )

    thumbnail_bytes = None
    thumbnail_url = info_dict.get("thumbnail")
    if thumbnail_url:
        try:
            response = requests.get(
                thumbnail_url, timeout=20, **_requests_kwargs(proxy_url)
            )
            response.raise_for_status()
            thumbnail_bytes = response.content
        except Exception:
            logger.warning("封面预览下载失败: %s", thumbnail_url, exc_info=True)

    return normalize_preview_data(url, info_dict, thumbnail_bytes)


class VideoPreviewThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str, download_engine_strategy: str | None = None):
        super().__init__()
        self.url = url
        self.download_engine_strategy = download_engine_strategy

    def run(self):
        try:
            self.finished.emit(extract_preview(self.url, self.download_engine_strategy))
        except Exception as exc:
            logger.exception("解析下载资源失败: %s", exc)
            self.error.emit(str(exc))


class VideoDownloadThread(QThread):
    finished = pyqtSignal(str)
    detailed_finished = pyqtSignal(dict)
    progress = pyqtSignal(int, str)
    progress_detail = pyqtSignal(dict)
    error = pyqtSignal(str)
    cancelled = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        work_dir: str,
        need_video: bool = True,
        need_subtitle: bool = True,
        need_thumbnail: bool = False,
        subtitle_mode: str = "auto",
        download_engine_strategy: str | None = None,
        download_mode: str = "video_audio",
        selected_video_format_id: str = "",
        selected_audio_format_id: str = "",
        format_selector: str = "",
        need_metadata: bool = False,
        need_description_txt: bool = False,
        need_transcript_txt: bool = False,
        enable_time_ranges: bool = False,
        download_sections: list[str] | None = None,
        pr_smart_transcode_hevc_on_av1: bool = False,
    ):
        super().__init__()
        self.url = url
        self.work_dir = work_dir
        self.need_video = need_video
        self.need_subtitle = need_subtitle
        self.need_thumbnail = need_thumbnail
        self.subtitle_mode = subtitle_mode if subtitle_mode in {"manual", "auto"} else "auto"
        self.download_engine_strategy = download_engine_strategy
        self.download_mode = download_mode
        self.selected_video_format_id = selected_video_format_id
        self.selected_audio_format_id = selected_audio_format_id
        self.format_selector = format_selector
        self.need_metadata = need_metadata
        self.need_description_txt = need_description_txt
        self.need_transcript_txt = need_transcript_txt
        self.enable_time_ranges = enable_time_ranges
        self.download_sections = list(download_sections or [])
        self.pr_smart_transcode_hevc_on_av1 = pr_smart_transcode_hevc_on_av1
        self._pause_event = threading.Event()
        self._terminate_event = threading.Event()
        self._pause_notice_emitted = False
        self._current_progress = 0
        self._download_root = Path(work_dir)
        self._download_dir = None
        self._download_dir_existed = False
        self._download_started_at = None

    def run(self):
        try:
            result = self.download(
                need_video=self.need_video,
                need_subtitle=self.need_subtitle,
                need_thumbnail=self.need_thumbnail,
                subtitle_mode=self.subtitle_mode,
                need_metadata=self.need_metadata,
                need_description_txt=self.need_description_txt,
                need_transcript_txt=self.need_transcript_txt,
                enable_time_ranges=self.enable_time_ranges,
                download_sections=self.download_sections,
                pr_smart_transcode_hevc_on_av1=self.pr_smart_transcode_hevc_on_av1,
            )
            self.detailed_finished.emit(result)
            self.finished.emit(result.get("video_path") or "")
        except DownloadCancelledError as exc:
            message = self._cleanup_partial_download(str(exc))
            logger.info(message)
            self.cancelled.emit(message)
        except Exception as exc:
            if self._terminate_event.is_set():
                message = self._cleanup_partial_download(self.tr("下载已终止，已清理当前下载数据。"))
                logger.info("%s 原始异常: %s", message, exc)
                self.cancelled.emit(message)
                return
            logger.exception("下载资源失败: %s", exc)
            self.error.emit(str(exc))

    def request_pause(self):
        if not self._terminate_event.is_set():
            self._pause_event.set()

    def request_terminate(self):
        self._terminate_event.set()

    def _raise_if_terminated(self):
        if self._terminate_event.is_set():
            raise DownloadCancelledError("下载已终止，正在清理当前下载数据。")

    def _cleanup_partial_download(self, default_message: str) -> str:
        target = self._download_dir
        base_dir = self._download_root
        if not target:
            return default_message

        try:
            base_resolved = base_dir.resolve(strict=False)
            target_resolved = target.resolve(strict=False)
            target_resolved.relative_to(base_resolved)
        except (OSError, ValueError):
            logger.warning("跳过清理下载目录，路径校验失败: base=%s target=%s", base_dir, target)
            return default_message

        if target_resolved == base_resolved:
            logger.warning("跳过清理下载目录，目标目录与输出根目录相同: %s", target_resolved)
            return default_message

        try:
            if not target_resolved.exists():
                return default_message

            if not self._download_dir_existed:
                shutil.rmtree(target_resolved)
                return "下载已终止，已清理当前下载目录。"

            cutoff = (self._download_started_at or time.time()) - 1
            files = sorted(
                (path for path in target_resolved.rglob("*") if path.is_file()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            removed_count = 0
            for path in files:
                try:
                    if path.stat().st_mtime >= cutoff:
                        path.unlink(missing_ok=True)
                        removed_count += 1
                except FileNotFoundError:
                    continue

            directories = sorted(
                (path for path in target_resolved.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            for directory in directories:
                try:
                    directory.rmdir()
                except OSError:
                    continue

            return (
                "下载已终止，已清理当前下载产生的数据。"
                if removed_count
                else default_message
            )
        except Exception as exc:
            logger.warning("清理下载目录失败: %s", exc)
            return f"{default_message} 清理残留时遇到问题: {exc}"

    def progress_hook(self, data):
        if data.get("status") != "downloading":
            return
        percent = data.get("_percent_str", "0")
        speed = data.get("_speed_str", "0")
        eta = data.get("_eta_str", "")
        downloaded_bytes = data.get("_downloaded_bytes_str", "")
        total_bytes = data.get("_total_bytes_str", "") or data.get("_total_bytes_estimate_str", "")
        elapsed = data.get("_elapsed_str", "")
        filename = data.get("filename") or data.get("info_dict", {}).get("title") or ""
        clean_percent = (
            str(percent).replace("\x1b[0;94m", "").replace("\x1b[0m", "").strip().replace("%", "")
        )
        clean_speed = str(speed).replace("\x1b[0;32m", "").replace("\x1b[0m", "").strip()
        clean_eta = str(eta).strip()
        clean_downloaded = str(downloaded_bytes).strip()
        clean_total = str(total_bytes).strip()
        clean_elapsed = str(elapsed).strip()

        try:
            progress_value = int(float(clean_percent))
        except ValueError:
            progress_value = 0
        self._current_progress = progress_value
        detail_payload = {
            "percent": clean_percent,
            "speed": clean_speed,
            "eta": clean_eta,
            "downloaded": clean_downloaded,
            "total": clean_total,
            "elapsed": clean_elapsed,
            "filename": str(filename),
        }
        self.progress_detail.emit(detail_payload)

        self._raise_if_terminated()

        if self._pause_event.is_set():
            if not self._pause_notice_emitted:
                self._pause_notice_emitted = True
                self.progress.emit(
                    self._current_progress,
                    "下载已暂停，再次点击按钮将终止下载并清理当前数据。",
                )
            while self._pause_event.is_set():
                self._raise_if_terminated()
                time.sleep(0.2)

        self.progress.emit(progress_value, f"下载进度: {clean_percent}%  速度: {clean_speed}")

    def _default_format_selector(self) -> str:
        return _robust_format_selector("", self.download_mode)

    def _effective_format_selector(self) -> str:
        if self.format_selector:
            return _robust_format_selector(self.format_selector, self.download_mode)
        if self.download_mode == "audio":
            return _robust_format_selector(
                self.selected_audio_format_id or self._default_format_selector(),
                self.download_mode,
            )
        if self.download_mode == "video":
            return _robust_format_selector(
                self.selected_video_format_id or self._default_format_selector(),
                self.download_mode,
            )
        if self.selected_video_format_id and self.selected_audio_format_id:
            return f"{self.selected_video_format_id}+{self.selected_audio_format_id}"
        if self.selected_video_format_id:
            return self.selected_video_format_id
        return self._default_format_selector()

    def _find_main_media_files(self, work_dir: Path) -> list[str]:
        candidates = []
        for file in work_dir.rglob("*"):
            if not file.is_file():
                continue
            if "subtitle" in {part.lower() for part in file.parts}:
                continue
            suffix = file.suffix.lower()
            if suffix in IMAGE_EXTENSIONS or suffix in SUBTITLE_EXTENSIONS:
                continue
            if suffix in {".json", ".part", ".ytdl", ".tmp", ".txt"}:
                continue
            candidates.append(file)

        if not candidates:
            return []

        if self.download_mode == "audio":
            audio_candidates = [file for file in candidates if file.suffix.lower() in AUDIO_EXTENSIONS]
            if audio_candidates:
                candidates = audio_candidates
        else:
            video_candidates = [file for file in candidates if file.suffix.lower() in VIDEO_EXTENSIONS]
            if video_candidates:
                candidates = video_candidates

        candidates.sort(key=lambda file: (file.stat().st_size, file.stat().st_mtime), reverse=True)
        return [str(file) for file in candidates]

    def _find_main_media_file(self, work_dir: Path) -> str | None:
        media_files = self._find_main_media_files(work_dir)
        return media_files[0] if media_files else None

    def _write_metadata_file(self, info_dict: dict, work_dir: Path) -> str:
        metadata_path = work_dir / f"{sanitize_filename(info_dict.get('title', 'video'))}.info.json"
        work_dir.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, "w", encoding="utf-8") as file:
            json.dump(info_dict, file, ensure_ascii=False, indent=2, default=str)
        return str(metadata_path)

    def _write_description_txt_file(self, info_dict: dict, work_dir: Path) -> str:
        return write_description_txt_file(
            info_dict,
            work_dir,
            sanitize_filename(info_dict.get("title", "video")),
        )

    def _write_transcript_txt_file(self, subtitle_path: str, info_dict: dict, work_dir: Path) -> str:
        return write_transcript_txt_file(
            subtitle_path,
            work_dir,
            sanitize_filename(info_dict.get("title", "video")),
        )

    def _postprocess_pr_smart_hevc(
        self, video_path: str | None
    ) -> tuple[str | None, str | None, str, bool, str | None, str | None]:
        if not self.pr_smart_transcode_hevc_on_av1:
            return None, None, "未启用", False, None, None
        if not video_path:
            return None, None, "未找到可转码的视频", False, None, None

        source_path = Path(video_path)
        target_path = source_path.with_name(f"{source_path.stem}-hevc.mp4")

        if not is_native_hevc_transcode_supported():
            return (
                None,
                None,
                "macOS 原生 H.265 转码不可用，可手动使用 FFmpeg 重试",
                True,
                str(source_path),
                str(target_path),
            )

        codec = get_native_video_codec(str(source_path))
        if codec != "av1":
            return None, None, f"未触发，当前编码为 {codec or '未知'}", False, None, None

        try:
            encoder = transcode_video_to_hevc_native(
                str(source_path),
                str(target_path),
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            logger.exception("macOS 原生 H.265 后处理失败: %s", exc)
            return (
                None,
                None,
                f"macOS 原生 H.265 后处理失败，可手动使用 FFmpeg 重试: {exc}",
                True,
                str(source_path),
                str(target_path),
            )
        return str(target_path), encoder, f"已使用 macOS 原生 API 转码为 H.265", False, None, None

    def download(
        self,
        need_video: bool = True,
        need_subtitle: bool = True,
        need_thumbnail: bool = False,
        subtitle_mode: str = "auto",
        need_metadata: bool = False,
        need_description_txt: bool = False,
        need_transcript_txt: bool = False,
        enable_time_ranges: bool = False,
        download_sections: list[str] | None = None,
        pr_smart_transcode_hevc_on_av1: bool = False,
    ) -> dict:
        logger.info("开始下载资源: %s", self.url)
        self._download_started_at = time.time()
        self._raise_if_terminated()
        proxy_url = apply_download_proxy_environment()
        cookiefile_path = APP_DATA_PATH / "cookies.txt"
        effective_strategy = _resolve_download_engine_strategy(
            self.download_engine_strategy, proxy_url, cookiefile_path
        )
        if effective_strategy:
            logger.info("下载引擎策略: %s", effective_strategy)

        info_dict = _extract_metadata_info(
            self.url, proxy_url, cookiefile_path, effective_strategy
        )
        active_cookiefile_path = (
            NO_COOKIE_FILE_PATH
            if info_dict.get("_videocaptioner_disable_cookiefile")
            else cookiefile_path
        )
        self._raise_if_terminated()
        title = sanitize_filename(info_dict.get("title", "MyVideo"))
        work_dir = Path(self.work_dir) / title
        self._download_dir = work_dir
        self._download_dir_existed = work_dir.exists()
        work_dir.mkdir(parents=True, exist_ok=True)
        self._raise_if_terminated()

        subtitle_language = info_dict.get("language")
        if subtitle_language:
            subtitle_language = str(subtitle_language).lower().split("-")[0]

        subtitle_download_link = None
        subtitle_ext = "vtt"
        effective_need_subtitle = need_subtitle or need_transcript_txt

        if effective_need_subtitle:
            subtitle_download_link, subtitle_ext = _pick_subtitle_item(
                info_dict, subtitle_mode, subtitle_language
            )

        fallback_proxy = proxy_url or get_effective_download_proxy_url()
        subtitle_path = None
        transcript_txt_path = None
        transcript_message = "未触发"
        terms_txt_path = None
        terms_message = "请在 WhisperX 热词管理中手动生成"
        if need_transcript_txt:
            self.progress.emit(2, self.tr("提前下载字幕并生成视频文稿..."))
            try:
                subtitle_path = _download_subtitle_fallback(
                    subtitle_download_link,
                    subtitle_ext,
                    work_dir / "subtitle" / f"【下载字幕】_{subtitle_language or subtitle_mode}",
                    fallback_proxy,
                )
                if subtitle_path:
                    transcript_txt_path = self._write_transcript_txt_file(
                        subtitle_path, info_dict, work_dir
                    )
                    transcript_message = "已提前生成"
                else:
                    transcript_message = "未找到可提前下载的字幕，稍后尝试生成视频文稿"
            except Exception as exc:
                logger.exception("提前生成视频文稿失败: %s", exc)
                transcript_message = f"提前生成视频文稿失败，稍后重试: {exc}"
            self._raise_if_terminated()

        ydl_need_subtitle = effective_need_subtitle and not subtitle_path
        options = _build_ydl_options(
            proxy_url, active_cookiefile_path, progress_hooks=[self.progress_hook]
        )
        options.update(_build_strategy_options(effective_strategy))
        options.update(
            {
                "outtmpl": {
                    "default": "%(title)s.%(ext)s",
                    "subtitle": "【下载字幕】.%(ext)s",
                    "thumbnail": "thumbnail",
                },
                "writesubtitles": ydl_need_subtitle and subtitle_mode == "manual",
                "writeautomaticsub": ydl_need_subtitle and subtitle_mode == "auto",
                "writethumbnail": need_thumbnail,
                "thumbnail_format": "png",
                "skip_download": not need_video,
            }
        )
        if need_video:
            options["format"] = self._effective_format_selector()
            logger.info("使用 format 选择器: %s", options["format"])
            if enable_time_ranges and download_sections:
                options["download_ranges"] = _build_download_ranges_callback(download_sections)
                logger.info("使用时间段下载: %s", " | ".join(download_sections))

        options["paths"] = {
            "home": str(work_dir),
            "subtitle": str(work_dir / "subtitle"),
            "thumbnail": str(work_dir),
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([self.url])
        except yt_dlp.utils.DownloadError as exc:
            fallback_selector = self._default_format_selector()
            current_selector = str(options.get("format") or "")
            if (
                need_video
                and fallback_selector
                and fallback_selector != current_selector
                and "Requested format is not available" in str(exc)
            ):
                logger.warning(
                    "指定格式不可用，改用默认格式选择器重试: %s -> %s",
                    current_selector,
                    fallback_selector,
                )
                options["format"] = fallback_selector
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([self.url])
            else:
                raise
        self._raise_if_terminated()

        media_files = self._find_main_media_files(work_dir) if need_video else []
        media_path = media_files[0] if len(media_files) == 1 else (str(work_dir) if media_files else None)
        if not subtitle_path:
            for file in work_dir.glob("**/【下载字幕】.*"):
                subtitle_path = str(file)
                break

        if effective_need_subtitle and not subtitle_path:
            subtitle_path = _download_subtitle_fallback(
                subtitle_download_link,
                subtitle_ext,
                work_dir / "subtitle" / f"【下载字幕】_{subtitle_language or subtitle_mode}",
                fallback_proxy,
            )

        thumbnail_path = None
        for file in work_dir.glob("**/thumbnail*"):
            thumbnail_path = str(file)
            break

        if need_thumbnail and not thumbnail_path:
            thumbnail_path = _download_thumbnail_fallback(
                info_dict.get("thumbnail"),
                work_dir / "thumbnail.jpg",
                fallback_proxy,
            )
        thumbnail_path = _normalize_thumbnail_to_png(thumbnail_path)

        metadata_path = self._write_metadata_file(info_dict, work_dir) if need_metadata else None
        description_txt_path = (
            self._write_description_txt_file(info_dict, work_dir)
            if need_video and need_description_txt
            else None
        )
        if need_transcript_txt and not transcript_txt_path:
            if subtitle_path:
                try:
                    transcript_txt_path = self._write_transcript_txt_file(
                        subtitle_path, info_dict, work_dir
                    )
                    transcript_message = "已生成"
                except Exception as exc:
                    logger.exception("视频文稿生成失败: %s", exc)
                    transcript_message = f"视频文稿生成失败: {exc}"
            else:
                transcript_message = "未下载到字幕，无法生成视频文稿"
        multi_media = len(media_files) > 1
        original_video_path = media_files[0] if self.download_mode != "audio" and len(media_files) == 1 else None
        transcoded_video_path = None
        transcoded_video_codec = None
        postprocess_message = "未触发"
        postprocess_failed = False
        postprocess_fallback_source_path = None
        postprocess_fallback_target_path = None
        preferred_media_path = media_path
        if need_video and not multi_media and self.download_mode != "audio" and pr_smart_transcode_hevc_on_av1:
            try:
                (
                    transcoded_video_path,
                    transcoded_video_codec,
                    postprocess_message,
                    postprocess_failed,
                    postprocess_fallback_source_path,
                    postprocess_fallback_target_path,
                ) = self._postprocess_pr_smart_hevc(
                    original_video_path
                )
                if transcoded_video_path:
                    preferred_media_path = transcoded_video_path
            except Exception as exc:
                logger.exception("PR智能预设后处理失败: %s", exc)
                postprocess_message = f"H.265 后处理失败: {exc}"
                postprocess_failed = True
                if original_video_path:
                    source_path = Path(original_video_path)
                    postprocess_fallback_source_path = str(source_path)
                    postprocess_fallback_target_path = str(
                        source_path.with_name(f"{source_path.stem}-hevc.mp4")
                    )

        result = {
            "video_path": transcoded_video_path or original_video_path,
            "audio_path": media_files[0] if self.download_mode == "audio" and len(media_files) == 1 else None,
            "media_path": preferred_media_path,
            "media_paths": media_files,
            "original_video_path": original_video_path,
            "transcoded_video_path": transcoded_video_path,
            "transcoded_video_codec": transcoded_video_codec,
            "postprocess_message": postprocess_message,
            "postprocess_failed": postprocess_failed,
            "postprocess_fallback_source_path": postprocess_fallback_source_path,
            "postprocess_fallback_target_path": postprocess_fallback_target_path,
            "subtitle_path": subtitle_path,
            "thumbnail_path": thumbnail_path,
            "metadata_path": metadata_path,
            "description_txt_path": description_txt_path,
            "transcript_txt_path": transcript_txt_path,
            "transcript_message": transcript_message,
            "terms_txt_path": terms_txt_path,
            "terms_message": terms_message,
            "info_dict": info_dict,
            "work_dir": str(work_dir),
            "url": self.url,
            "download_mode": self.download_mode,
            "format_selector": self._effective_format_selector() if need_video else "",
            "download_sections": list(download_sections or []),
            "has_multiple_media_files": multi_media,
        }
        logger.info(
            "下载完成: media=%s media_count=%s subtitle=%s thumbnail=%s metadata=%s description_txt=%s transcript_txt=%s terms_txt=%s",
            result["media_path"],
            len(media_files),
            subtitle_path,
            thumbnail_path,
            metadata_path,
            description_txt_path,
            transcript_txt_path,
            terms_txt_path,
        )
        return result
