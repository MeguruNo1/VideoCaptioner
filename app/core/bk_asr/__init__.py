from importlib import import_module

__all__ = ["MLXWhisperASR", "WhisperXASR", "whisper_x_auto", "transcribe"]


def transcribe(*args, **kwargs):
    from .transcribe import transcribe as _transcribe

    return _transcribe(*args, **kwargs)


def __getattr__(name):
    if name == "MLXWhisperASR":
        from .mlx_whisper import MLXWhisperASR

        return MLXWhisperASR
    if name == "WhisperXASR":
        from .whisper_x_auto import WhisperXASR

        return WhisperXASR
    if name == "whisper_x_auto":
        return import_module(".whisper_x_auto", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
