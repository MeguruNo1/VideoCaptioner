# VideoCaptioner macOS WhisperX CPU build

This build profile keeps the local transcription stack focused on WhisperX:

- ASR engine: WhisperX only
- Device: CPU only
- Word-level timestamps: enabled
- Alignment: enabled
- External bundled binaries under `resource/bin` are not required for ASR
- App data: `~/Library/Application Support/VideoCaptioner`
- Default work folder: `~/Movies/VideoCaptioner`

## Setup

Use Apple Silicon Python 3.11 or 3.12.

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-macos-whisperx.txt
python main.py
```

If you need to force the same WhisperX-only profile on a non-macOS machine:

```bash
VIDEOCAPTIONER_WHISPERX_ONLY=1 python main.py
```

## Runtime notes

WhisperX downloads Whisper, VAD, and alignment models on first use unless they
already exist under `~/Library/Application Support/VideoCaptioner/models`. CPU
mode should use `int8` by default for better speed and memory use on Apple
Silicon.
