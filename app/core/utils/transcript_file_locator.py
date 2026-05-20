from pathlib import Path
from typing import Iterable


SUPPORTED_TRANSCRIPT_SUFFIXES = {".txt", ".srt", ".vtt", ".ass", ".json"}
VIDEO_TRANSCRIPT_PATTERN = "【视频文稿】*.txt"
SUBTITLE_PATTERNS = (
    "subtitle/【原始字幕】*.srt",
    "subtitle/【下载字幕】*.srt",
    "subtitle/【下载字幕】*.vtt",
    "subtitle/【下载字幕】*.ass",
    "subtitle/【下载字幕】*.json",
    "【原始字幕】*.srt",
    "【下载字幕】*.srt",
    "【下载字幕】*.vtt",
    "【下载字幕】*.ass",
    "【下载字幕】*.json",
)


def _existing_supported_file(path: Path) -> Path | None:
    if path.is_file() and path.suffix.lower() in SUPPORTED_TRANSCRIPT_SUFFIXES:
        return path
    return None


def _newest(paths: Iterable[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def find_transcript_in_directory(directory: str | Path) -> Path | None:
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        return None

    direct_transcript = _newest(root.glob(VIDEO_TRANSCRIPT_PATTERN))
    if direct_transcript:
        return direct_transcript

    for pattern in SUBTITLE_PATTERNS:
        subtitle_path = _newest(root.glob(pattern))
        if subtitle_path:
            return subtitle_path

    recursive_transcript = _newest(root.rglob(VIDEO_TRANSCRIPT_PATTERN))
    if recursive_transcript:
        return recursive_transcript

    return None


def resolve_default_transcript_path(
    candidates: Iterable[str | Path | None],
    work_dir: str | Path | None = None,
) -> str:
    work_root = Path(work_dir) if work_dir else None

    for candidate in candidates:
        if not candidate:
            continue

        path = Path(candidate)
        supported_file = _existing_supported_file(path)
        if supported_file:
            return str(supported_file)

        search_dirs = []
        if path.is_dir():
            search_dirs.append(path)
        else:
            search_dirs.append(path.parent)
            if work_root:
                search_dirs.append(work_root / path.stem)

        for directory in search_dirs:
            transcript_path = find_transcript_in_directory(directory)
            if transcript_path:
                return str(transcript_path)

    if work_root:
        transcript_path = find_transcript_in_directory(work_root)
        if transcript_path:
            return str(transcript_path)
        if work_root.exists():
            return str(work_root)

    return ""
