import html
import json
import re
from pathlib import Path

from app.core.bk_asr.asr_data import ASRData, ASRDataSeg


_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_NO_SPACE_BEFORE = set(".,!?;:%)]}，。！？；：、）】》」』")
_NO_SPACE_AFTER = set("([{（【《「『")


def _clean_subtitle_text(text: str) -> str:
    value = html.unescape(str(text or ""))
    value = value.replace("\ufeff", "").replace("\u200b", "")
    value = _TAG_PATTERN.sub("", value)
    value = value.replace("\\N", " ").replace("\n", " ")
    value = _WHITESPACE_PATTERN.sub(" ", value)
    return value.strip()


def _normalize_for_dedupe(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text.strip()).casefold()


def _needs_space(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    left = previous[-1]
    right = current[0]
    if right in _NO_SPACE_BEFORE or left in _NO_SPACE_AFTER:
        return False
    if _CJK_PATTERN.search(left) or _CJK_PATTERN.search(right):
        return False
    return True


def _join_transcript_piece(paragraph: str, text: str) -> str:
    if not paragraph:
        return text
    separator = " " if _needs_space(paragraph, text) else ""
    return f"{paragraph}{separator}{text}"


def _load_json3_subtitle(file_path: Path) -> ASRData:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        data = json.loads(file_path.read_text(encoding="gbk"))

    segments = []
    for event in data.get("events") or []:
        text = "".join(str(seg.get("utf8") or "") for seg in event.get("segs") or [])
        text = _clean_subtitle_text(text)
        if not text:
            continue
        start_time = int(event.get("tStartMs") or 0)
        end_time = start_time + int(event.get("dDurationMs") or 0)
        segments.append(ASRDataSeg(text, start_time, end_time))
    return ASRData(segments)


def load_subtitle_asr_data(file_path: str | Path) -> ASRData:
    path = Path(file_path)
    if path.suffix.lower() == ".json3":
        return _load_json3_subtitle(path)
    return ASRData.from_subtitle_file(str(path))


def render_plain_transcript(asr_data: ASRData) -> str:
    pieces = []
    previous_key = ""
    for segment in asr_data:
        text = _clean_subtitle_text(segment.text)
        if not text:
            continue
        key = _normalize_for_dedupe(text)
        if key == previous_key:
            continue
        pieces.append((segment.start_time, text))
        previous_key = key

    if not pieces:
        raise ValueError("字幕文件中没有可生成文稿的内容")

    paragraphs = []
    current = ""
    previous_start_time = None
    for start_time, text in pieces:
        if current and previous_start_time is not None and start_time - previous_start_time > 8000:
            paragraphs.append(current)
            current = ""
        current = _join_transcript_piece(current, text)
        if len(current) >= 240 and re.search(r"[。！？.!?]$", text):
            paragraphs.append(current)
            current = ""
        previous_start_time = start_time

    if current:
        paragraphs.append(current)

    transcript = "\n\n".join(paragraphs).strip()
    if not transcript:
        raise ValueError("字幕文件中没有可生成文稿的内容")
    return transcript


def render_transcript_from_subtitle_file(file_path: str | Path) -> str:
    return render_plain_transcript(load_subtitle_asr_data(file_path))


def write_transcript_txt_file(
    subtitle_path: str | Path, work_dir: Path, filename_stem: str
) -> str:
    transcript_path = work_dir / f"【视频文稿】{filename_stem}.txt"
    work_dir.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        render_transcript_from_subtitle_file(subtitle_path),
        encoding="utf-8",
    )
    return str(transcript_path)
