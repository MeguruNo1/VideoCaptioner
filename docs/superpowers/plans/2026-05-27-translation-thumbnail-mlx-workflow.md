# Translation Thumbnail MLX Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add final subtitle over-length retranslation, normalize downloaded thumbnails to PNG, and improve the MLX Whisper workflow with preprocessing, chunking, VAD-aware segmentation, and global timestamp merging while excluding speaker diarization.

**Architecture:** Keep UI/config changes in existing settings and task factory paths. Keep translation retry inside the OpenAI-compatible translator so it can use the original subtitle text and current timing/context metadata. Add MLX workflow helpers next to the MLX ASR backend and keep the ASR entry point API stable for the rest of the app.

**Tech Stack:** Python, PyQt5/QFluentWidgets, yt-dlp, Pillow/PIL, torch/Silero optional, mlx-whisper, pytest/unittest.

---

- [ ] Add tests for source-only over-length final translation retry.
- [ ] Add translation config, task wiring, UI setting, cache isolation, and retry implementation.
- [ ] Add tests for thumbnail PNG normalization.
- [ ] Convert yt-dlp and fallback thumbnails to PNG and return the PNG path.
- [ ] Add tests for MLX chunk windows, timestamp offsetting, overlap dedupe, and transcribe wiring.
- [ ] Add MLX workflow config, UI controls, cache key coverage, preprocessing/chunking/VAD helpers, and ASR integration.
- [ ] Run focused tests for translation, download, MLX, config, and existing regression suites.
