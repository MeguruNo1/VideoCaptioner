import gc
import hashlib
import os

from ..utils.logger import setup_logger
from .asr_data import ASRDataSeg
from .base import BaseASR

logger = setup_logger("whisper_x")

LOCAL_ALIGN_MODEL_DIRS = {
    "en": "facebook-wav2vec2-base-960h",
    "zh": "jonatasgrosman-wav2vec2-large-xlsr-53-chinese-zh-cn",
}


class WhisperXASR(BaseASR):
    def __init__(
        self,
        audio_path: str,
        whisper_model: str = "large-v3",
        language: str = "en",
        device: str = "cuda",
        compute_type: str = "float16",
        batch_size: int = 8,
        align: bool = True,
        hf_token: str = None,
        model_dir: str = None,
        use_cache: bool = False,
        need_word_time_stamp: bool = False,
    ):
        super().__init__(audio_path, use_cache)
        self.whisper_model = whisper_model or "large-v3"
        self.language = language or None
        self.device = device or "cuda"
        self.compute_type = compute_type or "float16"
        self.batch_size = batch_size or 8
        self.align = align
        self.hf_token = hf_token or ""
        self.model_dir = model_dir
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
                )
            )

        return segments

    def _run(self, callback=None) -> dict:
        if callback is None:
            callback = lambda x, y: None

        try:
            import whisperx
        except ImportError as exc:
            raise RuntimeError(
                "WhisperX 未安装。请先安装 whisperx 及其依赖后再使用该转录模型。"
            ) from exc

        if self.hf_token:
            os.environ["HF_TOKEN"] = self.hf_token
            os.environ["HUGGINGFACE_TOKEN"] = self.hf_token

        model = None
        align_model = None

        try:
            callback(5, "加载 WhisperX")
            audio = whisperx.load_audio(self.audio_path)

            callback(15, "加载转录模型")
            model = self._load_transcribe_model(whisperx)

            callback(35, "WhisperX 转录中")
            result = self._transcribe(model, audio)

            need_align = bool(result.get("segments")) and (
                self.align or self.need_word_time_stamp
            )
            if need_align:
                callback(70, "WhisperX 对齐中")
                align_model, metadata = self._load_align_model(
                    whisperx, result.get("language") or self.language
                )
                result = whisperx.align(
                    result["segments"],
                    align_model,
                    metadata,
                    audio,
                    self.device,
                    return_char_alignments=False,
                )

            callback(100, "WhisperX 完成")
            return result
        finally:
            del model
            del align_model
            gc.collect()

            try:
                import torch

                if self.device == "cuda" and torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def _load_transcribe_model(self, whisperx):
        kwargs = {
            "compute_type": self.compute_type,
        }
        if self.language:
            kwargs["language"] = self.language
        if self.model_dir:
            kwargs["download_root"] = self.model_dir

        try:
            return whisperx.load_model(self.whisper_model, self.device, **kwargs)
        except TypeError:
            kwargs.pop("download_root", None)
            return whisperx.load_model(self.whisper_model, self.device, **kwargs)

    def _transcribe(self, model, audio):
        kwargs = {"batch_size": self.batch_size}
        if self.language:
            kwargs["language"] = self.language

        try:
            return model.transcribe(audio, **kwargs)
        except TypeError:
            kwargs.pop("language", None)
            return model.transcribe(audio, **kwargs)

    def _load_align_model(self, whisperx, language_code: str):
        kwargs = {
            "language_code": language_code,
            "device": self.device,
        }
        if self.model_dir:
            kwargs["model_dir"] = self.model_dir
            local_dir_name = LOCAL_ALIGN_MODEL_DIRS.get(language_code)
            if local_dir_name:
                local_model_dir = os.path.join(self.model_dir, local_dir_name)
                if os.path.isdir(local_model_dir):
                    kwargs["model_name"] = local_model_dir

        try:
            return whisperx.load_align_model(**kwargs)
        except TypeError:
            kwargs.pop("model_dir", None)
            return whisperx.load_align_model(**kwargs)

    def _get_key(self):
        payload = "|".join(
            [
                self.crc32_hex,
                self.whisper_model,
                str(self.language),
                self.device,
                self.compute_type,
                str(self.batch_size),
                str(self.align),
                str(self.need_word_time_stamp),
            ]
        )
        return hashlib.md5(payload.encode("utf-8")).hexdigest()
