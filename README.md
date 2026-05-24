# VideoCaptioner

VideoCaptioner is a desktop video captioning tool that transcribes, translates, and processes subtitles using state-of-the-art speech recognition and large language models.

## Features

- **Multi-engine ASR** — Supports FasterWhisper, WhisperX, WhisperCpp, Whisper API, and more
- **macOS Apple Silicon profile** — Supports a focused WhisperX CPU build with word-level timestamps enabled
- **LLM-powered subtitle processing** — AI-driven translation, optimization, splitting, and summarization using OpenAI, DeepSeek, Gemini, Ollama, and other LLM providers
- **Subtitle translation** — Built-in DeepLx, Microsoft, and Google translation backends, plus LLM-based translation
- **Smart subtitle splitting** — Semantic and sentence-level splitting with CJK and English word count limits
- **Rich language support** — 80+ target languages for transcription and translation
- **Subtitle style editor** — Customize subtitle appearance and export in SRT, ASS, VTT, JSON, and TXT formats
- **Video download** — Integrated video download center
- **Hotword / glossary** — WhisperX hotword support and AI term extraction for improved transcription accuracy

## Installation

Download the latest release from the [Releases](https://github.com/WEIFENG2333/VideoCaptioner/releases) page.

### Prerequisites

#### Windows release

- Windows 10/11
- NVIDIA GPU with CUDA support (recommended for FasterWhisper and WhisperX)
- VLC media player

#### macOS Apple Silicon source build

- Apple Silicon Mac
- Python 3.11 recommended
- Homebrew `ffmpeg`
- WhisperX runs on CPU in this branch profile

### From Source

#### Windows / default source profile

```bash
git clone https://github.com/WEIFENG2333/VideoCaptioner.git
cd VideoCaptioner
pip install -r requirements.txt
python main.py
```

#### macOS Apple Silicon / WhisperX CPU profile

This branch includes a focused macOS profile for WhisperX-only local transcription:

- ASR engine is fixed to WhisperX
- Device is fixed to CPU
- Word-level timestamps are always enabled
- WhisperX alignment is always enabled
- CUDA, FasterWhisper, WhisperCpp, Whisper API, and Windows-only ASR entry points are hidden from the macOS UI

Install and run:

```bash
brew install python@3.11 ffmpeg git
git clone https://github.com/MeguruNo1/VideoCaptioner.git
cd VideoCaptioner
git checkout codex/mac
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-macos-whisperx.txt
python main.py
```

The same profile can be forced on non-macOS systems for development:

```bash
VIDEOCAPTIONER_WHISPERX_ONLY=1 python main.py
```

WhisperX downloads transcription, VAD, and alignment models on first use unless compatible local models already exist under `AppData/models`. For Apple Silicon CPU use, start with `small` or `medium`; `large-v3` works but is much slower and uses more memory.

## Supported Formats

| Type     | Formats                                                        |
| -------- | -------------------------------------------------------------- |
| Video    | MP4, MKV, MOV, AVI, WebM, WMV, FLV, TS, and 15 more           |
| Audio    | MP3, WAV, AAC, FLAC, OGG, OPUS, M4A, WMA, and 12 more         |
| Subtitle | SRT, ASS, VTT, JSON, TXT                                       |

## Supported ASR Engines

| Engine        | Windows/default profile                  | macOS Apple Silicon profile             |
| ------------- | ---------------------------------------- | --------------------------------------- |
| WhisperX      | Supported, CUDA or CPU depending on setup | Supported, CPU only, word timestamps on |
| FasterWhisper | Supported                                | Hidden in this branch profile           |
| WhisperCpp    | Supported                                | Hidden in this branch profile           |
| Whisper API   | Supported                                | Hidden in this branch profile           |

## Supported LLM Providers

OpenAI, DeepSeek, SiliconCloud, Ollama, LM Studio, Gemini, ChatGLM, Qwen

## License

This project is licensed under the terms of the original repository.

## Credits

Originally created by [@WEIFENG2333](https://github.com/WEIFENG2333). This repository is a community-maintained fork with additional features and improvements.
