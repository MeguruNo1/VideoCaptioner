from app.config import WHISPERX_ONLY_MODE

from .transcribe import transcribe
from .whisper_x_auto import WhisperXASR

if WHISPERX_ONLY_MODE:
    __all__ = ["whisper_x_auto", "transcribe"]
else:
    from .bcut import BcutASR
    from .faster_whisper import FasterWhisperASR
    from .jianying import JianYingASR
    from .kuaishou import KuaiShouASR
    from .whisper_api import WhisperAPI
    from .whisper_cpp import WhisperCppASR

    __all__ = [
        "bcut",
        "jianying",
        "kuaishou",
        "whisper_cpp",
        "whisper_api",
        "faster_whisper",
        "whisper_x",
        "whisper_x_auto",
        "transcribe",
    ]
