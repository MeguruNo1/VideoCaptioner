# VideoCaptioner macOS

This branch is a macOS-focused VideoCaptioner build for Apple Silicon. It keeps
the local ASR path intentionally narrow: WhisperX on CPU with word-level
timestamps and alignment enabled.

## Features

- **WhisperX-only local transcription** — CPU mode, `int8` by default
- **Word-level timestamps** — Always enabled for downstream splitting and timing
- **WhisperX alignment** — Always enabled for more stable timestamps
- **Subtitle processing** — Split, optimize, translate, and export subtitles
- **LLM integrations** — OpenAI-compatible providers for translation and cleanup
- **Video downloads** — yt-dlp based download center with browser cookie support
- **macOS storage paths** — App data under `~/Library/Application Support/VideoCaptioner`, work files under `~/Movies/VideoCaptioner`

## Requirements

- Apple Silicon Mac
- Python 3.11 recommended
- Homebrew
- `ffmpeg`

```bash
brew install python@3.11 ffmpeg git
```

## Run From Source

```bash
git clone https://github.com/MeguruNo1/VideoCaptioner.git
cd VideoCaptioner
git checkout codex/mac
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-macos-whisperx.txt
python main.py
```

WhisperX downloads transcription, VAD, and alignment models on first use unless
compatible local models already exist under:

```text
~/Library/Application Support/VideoCaptioner/models
```

Start with `small` or `medium` on CPU. `large-v3` can run, but it is much slower
and uses more memory.

## Supported Formats

| Type     | Formats                                              |
| -------- | ---------------------------------------------------- |
| Video    | MP4, MKV, MOV, AVI, WebM, WMV, FLV, TS, and more     |
| Audio    | MP3, WAV, AAC, FLAC, OGG, OPUS, M4A, WMA, and more   |
| Subtitle | SRT, ASS, VTT, JSON, TXT                             |

## macOS Notes

- The branch does not ship a bundled Windows runtime or Windows executables.
- The app uses the system `ffmpeg` from Homebrew.
- Browser cookies are exported through yt-dlp browser integration, trying Chrome, Edge, then Safari.
- The branch is prepared for a later `.app` packaging pass; source execution is the current supported path.

## License

This project is licensed under the terms of the original repository.

## Credits

Originally created by [@WEIFENG2333](https://github.com/WEIFENG2333). This fork
contains macOS-focused changes for a WhisperX CPU workflow.
