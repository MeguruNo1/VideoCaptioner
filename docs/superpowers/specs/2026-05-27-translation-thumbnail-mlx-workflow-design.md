# Translation, Thumbnail, And MLX Workflow Design

## Scope

Implement three user-facing improvements on `codex/mac`:

- Automatically retranslate final subtitles whose translated text exceeds a user-configured character threshold.
- Save downloaded video thumbnails as PNG.
- Improve the MLX Whisper workflow with audio preprocessing, VAD, long-audio chunking, overlap handling, and timestamp merging, while explicitly excluding speaker diarization.

The already-merged `codex/mlx-whisper` branch is the base. The old local `codex/mlx-whisper` branch has been deleted.

## Final Subtitle Retranslation

Add a new translation setting named `final_translation_rework_max_chars`.

- Default: `40`.
- `0` disables the feature.
- The setting applies to OpenAI-compatible translation output after normal batch/single translation has produced final translated text.
- Detection uses the final `translated_text` character count after trimming whitespace and removing line breaks.
- Only subtitles over the configured threshold are retried.

The retry must translate from the original subtitle text only. It must not include or reference the current translated text. The retry prompt will include:

- original subtitle text,
- target language,
- the configured maximum character count,
- relevant timing/readability context when available,
- existing document prompt or filtered terminology context when already used by the translation flow.

The retry prompt must explicitly say to translate again from the original, preserve full meaning, avoid summarizing, and keep the result within the configured character count where possible. It may mention that the previous attempt was too long, but it must not provide the previous translation.

Each overlong subtitle gets at most one source-only retranslation attempt. If the retry still exceeds the threshold, keep the retry result rather than truncating it. If the retry fails or returns an empty/error result, keep the original translated result.

## Thumbnail PNG

Downloaded thumbnails should resolve to a PNG path.

- Configure yt-dlp to prefer PNG output where supported.
- After yt-dlp or fallback download, normalize the thumbnail file to `thumbnail.png`.
- Use Pillow for conversion.
- If conversion fails, keep the original file and log a warning; video/subtitle download should still succeed.
- Result UI should display the normalized PNG path when conversion succeeds.

## MLX Whisper Workflow

Keep the current `mlx_whisper.transcribe` backend and existing hotword/initial prompt behavior. Do not introduce speaker diarization or speaker labels.

Add a preprocessing workflow inspired by `ZYDTR/MLX-Whisper`:

- Convert input audio to mono 16 kHz PCM for MLX processing.
- Optionally run VAD to skip non-speech intervals.
- Split long audio into configurable chunks.
- Add configurable overlap between chunks to avoid cutting speech.
- Convert each chunk result back to global timestamps.
- Merge chunk outputs and drop duplicated overlap words/segments.
- Preserve word-level timestamps when enabled.

Add MLX settings:

- Enable MLX VAD, default on.
- VAD threshold, default conservative.
- Chunk length in seconds, default around 600.
- Chunk overlap in seconds, default around 30.

The workflow should fall back to current direct `mlx_whisper.transcribe` behavior if preprocessing dependencies are unavailable or the audio cannot be prepared.

## Tests

Add focused tests for:

- over-threshold final translations trigger source-only retranslation;
- retry prompts do not include the previous translation;
- threshold `0` disables retranslation;
- thumbnail normalization converts downloaded image paths to `.png`;
- MLX chunk timestamp offsets are applied correctly;
- MLX overlap duplicate removal keeps ordered output;
- existing MLX hotword and initial prompt behavior remains unchanged.

## Non-Goals

- No speaker diarization.
- No forced hard truncation of translations.
- No replacement of `mlx_whisper` with `lightning-whisper-mlx`.
- No full UI redesign.
