import gc
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]


def sanitize_sys_path():
    blocked = {
        str(SCRIPT_DIR).lower(),
        str(PROJECT_ROOT).lower(),
        "",
    }
    sys.path[:] = [
        p for p in sys.path if str(Path(p).resolve()).lower() not in blocked
    ]


def progress(value: int, message: str):
    print(f"PROGRESS\t{value}\t{message}", flush=True)


def _should_fallback_vad(exc: Exception, vad_method: str) -> bool:
    if (vad_method or "silero") != "silero":
        return False

    message = str(exc).lower()
    keywords = (
        "silero-vad",
        "torch.hub",
        "github.com/snakers4/silero-vad",
        "http error",
        "bad gateway",
        "urlopen",
        "temporary failure",
    )
    return any(keyword in message for keyword in keywords)


def _should_soft_fail_diarization(exc: Exception) -> bool:
    message = str(exc).lower()
    keywords = (
        "huggingface.co",
        "requests.exceptions.sslerror",
        "ssl: certificate_verify_failed",
        "certificate verify failed",
        "maxretryerror",
        "hf_hub_download",
        "speaker-diarization-community-1",
        "401 client error",
        "403 client error",
        "repository not found",
        "connection error",
    )
    return any(keyword in message for keyword in keywords)


def _resolve_local_silero_dir(
    local_silero_dir: str | None, strict: bool = False
) -> str | None:
    if not local_silero_dir:
        return None

    repo_dir = Path(local_silero_dir)
    if repo_dir.is_dir() and (repo_dir / "hubconf.py").is_file():
        return str(repo_dir)
    if repo_dir.is_dir():
        nested_repos = [p for p in repo_dir.iterdir() if p.is_dir() and (p / "hubconf.py").is_file()]
        if len(nested_repos) == 1:
            return str(nested_repos[0])

    if strict:
        raise RuntimeError(
            f"Invalid local Silero repository directory: {local_silero_dir}"
        )
    return None


def _resolve_local_diarize_dir(
    local_diarize_dir: str | None, strict: bool = False
) -> str | None:
    if not local_diarize_dir:
        return None

    checkpoint = Path(local_diarize_dir)
    if checkpoint.is_file() and checkpoint.name.lower() == "config.yaml":
        return str(checkpoint)
    if checkpoint.is_dir() and (checkpoint / "config.yaml").is_file():
        return str(checkpoint)
    if checkpoint.is_dir():
        nested_configs = []
        for item in checkpoint.iterdir():
            if item.is_file() and item.name.lower() == "config.yaml":
                nested_configs.append(item)
            elif item.is_dir() and (item / "config.yaml").is_file():
                nested_configs.append(item)
        if len(nested_configs) == 1:
            return str(nested_configs[0])

    if strict:
        raise RuntimeError(
            f"Invalid local diarization model directory: {local_diarize_dir}"
        )
    return None


def build_local_silero_vad(whisperx, repo_dir: str, vad_onset: float, chunk_size: int = 30):
    import torch
    from whisperx.diarize import Segment as SegmentX
    from whisperx.vads import Vad

    class LocalSileroVad(Vad):
        def __init__(self, local_repo_dir: str, **kwargs):
            super().__init__(kwargs["vad_onset"])
            self.vad_onset = kwargs["vad_onset"]
            self.chunk_size = kwargs["chunk_size"]
            self.vad_pipeline, vad_utils = torch.hub.load(
                repo_or_dir=local_repo_dir,
                model="silero_vad",
                source="local",
                force_reload=False,
                onnx=False,
                trust_repo=True,
            )
            (self.get_speech_timestamps, _, self.read_audio, _, _) = vad_utils

        def __call__(self, audio, **kwargs):
            sample_rate = audio["sample_rate"]
            if sample_rate != 16000:
                raise ValueError("Only 16000Hz sample rate is allowed")

            timestamps = self.get_speech_timestamps(
                audio["waveform"],
                model=self.vad_pipeline,
                sampling_rate=sample_rate,
                max_speech_duration_s=self.chunk_size,
                threshold=self.vad_onset,
            )
            return [
                SegmentX(i["start"] / sample_rate, i["end"] / sample_rate, "UNKNOWN")
                for i in timestamps
            ]

        @staticmethod
        def preprocess_audio(audio):
            return audio

        @staticmethod
        def merge_chunks(segments_list, chunk_size, onset=0.5, offset=None):
            if len(segments_list) == 0:
                return []
            return Vad.merge_chunks(segments_list, chunk_size, onset, offset)

    print(f"Using local Silero VAD repository: {repo_dir}", flush=True)
    return LocalSileroVad(repo_dir, vad_onset=vad_onset, chunk_size=chunk_size)


def load_transcribe_model(whisperx, request: dict):
    model_name = request.get("whisper_model_path") or request["whisper_model"]
    kwargs = {
        "compute_type": request["compute_type"],
    }
    if request.get("language"):
        kwargs["language"] = request["language"]
    if request.get("model_dir"):
        kwargs["download_root"] = request["model_dir"]
    asr_options = {}
    if request.get("hotwords"):
        asr_options["hotwords"] = request["hotwords"]
    if request.get("initial_prompt"):
        asr_options["initial_prompt"] = request["initial_prompt"]
    if asr_options:
        kwargs["asr_options"] = asr_options
    kwargs["vad_method"] = request.get("vad_method") or "silero"
    kwargs["vad_options"] = {
        "vad_onset": request.get("vad_threshold", 0.5)
    }
    local_silero_dir = _resolve_local_silero_dir(
        request.get("local_silero_dir"),
        strict=bool(request.get("local_silero_dir")),
    )
    if kwargs["vad_method"] == "silero" and local_silero_dir:
        kwargs["vad_model"] = build_local_silero_vad(
            whisperx,
            local_silero_dir,
            request.get("vad_threshold", 0.5),
        )

    def _load_once(load_kwargs: dict):
        try:
            return whisperx.load_model(model_name, request["device"], **load_kwargs)
        except TypeError:
            load_kwargs = dict(load_kwargs)
            load_kwargs.pop("download_root", None)
            return whisperx.load_model(model_name, request["device"], **load_kwargs)

    try:
        return _load_once(kwargs)
    except Exception as exc:
        if _should_fallback_vad(exc, kwargs.get("vad_method")):
            print(
                "WhisperX silero VAD load failed, falling back to pyannote VAD.",
                flush=True,
            )
            retry_kwargs = dict(kwargs)
            retry_kwargs.pop("vad_model", None)
            retry_kwargs["vad_method"] = "pyannote"
            return _load_once(retry_kwargs)
        raise


def transcribe(model, audio, request: dict):
    kwargs = {"batch_size": request["batch_size"]}
    if request.get("language"):
        kwargs["language"] = request["language"]

    try:
        return model.transcribe(audio, **kwargs)
    except TypeError:
        kwargs.pop("language", None)
        return model.transcribe(audio, **kwargs)


def load_align_model(whisperx, request: dict, language_code: str):
    kwargs = {
        "language_code": language_code,
        "device": request["device"],
    }

    model_dir = request.get("model_dir")
    if model_dir:
        kwargs["model_dir"] = model_dir
        local_name = (request.get("local_align_model_dirs") or {}).get(language_code)
        if local_name:
            local_model_dir = Path(model_dir) / local_name
            if local_model_dir.is_dir():
                kwargs["model_name"] = str(local_model_dir)

    try:
        return whisperx.load_align_model(**kwargs)
    except TypeError:
        kwargs.pop("model_dir", None)
        return whisperx.load_align_model(**kwargs)


def diarize(whisperx, request: dict, audio, result: dict):
    from whisperx.diarize import DiarizationPipeline, assign_word_speakers

    local_diarize_dir = _resolve_local_diarize_dir(
        request.get("local_diarize_dir"),
        strict=bool(request.get("local_diarize_dir")),
    )
    diarizer = DiarizationPipeline(
        model_name=local_diarize_dir,
        token=(request.get("hf_token") or None),
        device=request["device"],
        cache_dir=request.get("model_dir"),
    )
    diarize_df = diarizer(audio)
    return assign_word_speakers(diarize_df, result)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: whisperx_runner.py <request.json> <result.json>")

    request_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    request = json.loads(request_path.read_text(encoding="utf-8"))

    hf_token = request.get("hf_token") or ""
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
        os.environ["HUGGINGFACE_TOKEN"] = hf_token

    sanitize_sys_path()

    progress(10, "Loading WhisperX module")
    import torch
    import whisperx

    model = None
    align_model = None

    try:
        progress(20, "Loading audio")
        audio = whisperx.load_audio(request["audio_path"])

        progress(35, "Loading transcription model")
        model = load_transcribe_model(whisperx, request)

        progress(55, "Running transcription")
        result = transcribe(model, audio, request)

        need_align = bool(result.get("segments")) and (
            request.get("align") or request.get("need_word_time_stamp")
        )
        if need_align:
            progress(75, "Running alignment")
            align_model, metadata = load_align_model(
                whisperx, request, result.get("language") or request.get("language")
            )
            result = whisperx.align(
                result["segments"],
                align_model,
                metadata,
                audio,
                request["device"],
                return_char_alignments=False,
            )

        if request.get("diarize") and result.get("segments"):
            progress(88, "Running speaker diarization")
            try:
                result = diarize(whisperx, request, audio, result)
            except Exception as exc:
                if _should_soft_fail_diarization(exc):
                    print(
                        f"WhisperX speaker diarization skipped: {exc}",
                        flush=True,
                    )
                    progress(90, "Skipping speaker diarization")
                else:
                    raise

        progress(95, "Writing result")
        result_path.write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
        progress(100, "Done")
    finally:
        del model
        del align_model
        gc.collect()
        if request.get("device") == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
