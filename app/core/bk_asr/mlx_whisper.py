import gc
import hashlib

from ..utils.logger import setup_logger
from .asr_data import ASRDataSeg
from .base import BaseASR

logger = setup_logger("mlx_whisper")

DEFAULT_MLX_MODEL = "mlx-community/whisper-large-v3-turbo"


def _parse_prompt_terms(text: str) -> list[str]:
    terms = []
    for raw_line in (text or "").replace("，", ",").splitlines():
        for raw_term in raw_line.split(","):
            term = raw_term.strip()
            if term and term not in terms:
                terms.append(term)
    return terms


def build_mlx_initial_prompt(initial_prompt: str | None, hotwords: str | None) -> str:
    parts = []
    initial_prompt = (initial_prompt or "").strip()
    if initial_prompt:
        parts.append(initial_prompt)

    hotword_terms = _parse_prompt_terms(hotwords or "")
    if hotword_terms:
        parts.append(
            "以下专有名词或短语可能出现在音频中，请优先按这些写法识别："
            + ", ".join(hotword_terms)
        )

    return "\n".join(parts)


class MLXWhisperASR(BaseASR):
    def __init__(
        self,
        audio_path: str,
        model: str = DEFAULT_MLX_MODEL,
        language: str = "en",
        initial_prompt: str = "",
        use_cache: bool = False,
        need_word_time_stamp: bool = True,
    ):
        super().__init__(audio_path, use_cache)
        self.model = model or DEFAULT_MLX_MODEL
        self.language = language or None
        self.initial_prompt = (initial_prompt or "").strip()
        self.need_word_time_stamp = need_word_time_stamp

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        segments = []

        if self.need_word_time_stamp:
            for segment in resp_data.get("segments", []):
                for word in segment.get("words", []) or []:
                    text = (word.get("word") or word.get("text") or "").strip()
                    start = word.get("start")
                    end = word.get("end")
                    if not text or start is None or end is None:
                        continue
                    segments.append(
                        ASRDataSeg(
                            text=text,
                            start_time=int(float(start) * 1000),
                            end_time=int(float(end) * 1000),
                            speaker=word.get("speaker") or segment.get("speaker") or "",
                        )
                    )

        if segments:
            return segments

        for segment in resp_data.get("segments", []):
            text = (segment.get("text") or "").strip()
            start = segment.get("start")
            end = segment.get("end")
            if not text or start is None or end is None:
                continue
            segments.append(
                ASRDataSeg(
                    text=text,
                    start_time=int(float(start) * 1000),
                    end_time=int(float(end) * 1000),
                    speaker=segment.get("speaker") or "",
                )
            )

        return segments

    def _run(self, callback=None) -> dict:
        if callback is None:
            callback = lambda x, y: None

        try:
            import mlx_whisper
        except ImportError as exc:
            raise RuntimeError(
                "MLX Whisper 未安装。请先安装 mlx-whisper 后再使用该转录模型。"
            ) from exc

        try:
            callback(5, "Loading MLX Whisper")
            callback(35, "Transcribing with MLX Whisper")
            result = mlx_whisper.transcribe(
                self.audio_path,
                path_or_hf_repo=self.model,
                language=self.language,
                word_timestamps=self.need_word_time_stamp,
                initial_prompt=self.initial_prompt or None,
            )
            callback(100, "MLX Whisper finished")
            return result
        finally:
            gc.collect()

    def _get_key(self):
        payload = "|".join(
            [
                self.crc32_hex,
                self.model,
                str(self.language),
                self.initial_prompt,
                str(self.need_word_time_stamp),
            ]
        )
        return hashlib.md5(payload.encode("utf-8")).hexdigest()
