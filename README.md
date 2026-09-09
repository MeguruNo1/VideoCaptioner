<div align="center">

# VideoCaptioner macOS Fork

**语言 / Language:** 简体中文 | [English](./README.en.md)

</div>

这是 [WEIFENG2333/VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner) 的 macOS/Apple Silicon 本地工作流分支。它不是原项目的完整替代版，而是保留桌面端字幕处理体验，并针对 macOS 本地转写、下载、字幕切分和翻译稳定性做了较大幅度的裁剪与增强。

本 README 只说明本分支相对原项目的主要差异。原项目的完整介绍、在线文档、CLI 用法和发布版请以 [上游仓库](https://github.com/WEIFENG2333/VideoCaptioner) 为准。

## 与原项目的主要差异

| 方向 | 原项目 | 本分支 |
| --- | --- | --- |
| 项目定位 | 跨平台 CLI + GUI + PyPI 包 + 文档站 | macOS 本地源码运行的 GUI 分支 |
| 支持平台 | Windows、macOS、Linux | 仅支持 macOS，启动时会拒绝非 macOS 平台 |
| 本地 ASR | 多后端：`faster-whisper`、`whisper-api`、必剪、剪映、`whisper-cpp` 等 | 聚焦 WhisperX CPU，并新增 MLX Whisper 作为 Apple Silicon GPU 后端 |
| 时间戳策略 | 根据不同 ASR 后端能力处理 | 默认围绕词级时间戳、VAD 和 WhisperX 对齐构建后续字幕流程 |
| 下载流程 | 上游通用下载命令和桌面入口 | 独立下载中心，强化 yt-dlp、浏览器 Cookie、最终 MP4 归一化和 HEVC 兜底 |
| 字幕处理 | 上游通用字幕切分、优化、翻译和合成 | 增强严格断句、短间隙处理、重复 ASR 片段清理、术语/热词传递和 LLM 翻译稳定性 |
| 运行方式 | `pip install videocaptioner`、`uv run videocaptioner`、CLI/GUI 均可用 | 使用本仓库源码、`.venv` 和本地 `.app` 启动器运行 |
| 打包与文档 | 保留上游 PyPI、CI、VitePress 文档站和多平台构建脚本 | 删除或弱化上游发布链路，保留更小的 macOS 本地运行说明 |

## 本分支重点

- 面向 Apple Silicon Mac 的本地字幕工作流。
- WhisperX CPU 转写，默认使用 `int8`，并支持 WhisperX 对齐。
- 可选 MLX Whisper 后端，通过 `mlx-whisper` 使用 Apple Silicon GPU。
- 应用数据存放在 `~/Library/Application Support/VideoCaptioner`。
- 默认工作文件存放在 `~/Movies/VideoCaptioner`。
- 本地 `.app` 启动器直接运行当前源码目录里的 `.venv/bin/python main.py`。

## 当前不作为重点

- 不再以 PyPI 包和 `videocaptioner` CLI 作为主要入口。
- 不维护上游完整文档站、Release 工作流和多平台打包链路。
- 不追求覆盖上游所有 ASR、TTS、CLI 和跨平台功能。

## 下载发布版

本 fork 的发布版面向 Apple Silicon Mac，提供 `.dmg` 安装包：

```text
https://github.com/MeguruNo1/video-captioner-macos-enhanced/releases
```

安装方式：

1. 下载最新的 `VideoCaptioner-macos-enhanced-*.dmg`。
2. 打开 DMG，把 `VideoCaptioner.app` 拖到 `Applications`。
3. 如果 macOS 首次启动拦截，右键点击 `VideoCaptioner.app`，选择“打开”。

发布版会打包 Python 应用运行时和 Python 依赖，但不会内置 FFmpeg、WhisperX/MLX Whisper 模型或用户配置。处理媒体前仍建议安装 FFmpeg：

```bash
brew install ffmpeg
```

WhisperX 和 MLX Whisper 模型会在首次使用时下载，或读取已有的本地模型目录：

```text
~/Library/Application Support/VideoCaptioner/models
```

## 从源码运行

```bash
brew install python@3.12 ffmpeg git

git clone https://github.com/MeguruNo1/video-captioner-macos-enhanced.git
cd video-captioner-macos-enhanced

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-macos-whisperx.txt
python main.py
```

YouTube 现在可能要求字幕专用的 PO Token。首次从源码运行后，执行下面的脚本安装本地 Token provider；否则部分明明能在浏览器播放的自动字幕可能无法被 yt-dlp 列出：

```bash
scripts/setup_youtube_pot_provider.sh
```

该脚本需要 Node.js 20+、npm 和 Git，并将 provider 安装到
`~/Library/Application Support/VideoCaptioner/youtube-pot-provider`，不会在后台启动常驻服务。

WhisperX 首次使用时会下载转写、VAD 和对齐模型，除非已经存在兼容的本地模型：

```text
~/Library/Application Support/VideoCaptioner/models
```

`large-v3-turbo` 是这个分支默认的本地模型。建议将它放在应用模型目录下，并命名为 `faster-whisper-large-v3-turbo`。

MLX Whisper 默认使用 `mlx-community/whisper-large-v3-turbo`。也可以使用 Hugging Face 上的其他 MLX Whisper 模型，或使用通过 `mlx-examples/whisper` 转换得到的本地 MLX Whisper 模型目录。

## 安装本地 App 启动器

本地 app bundle 只是当前源码目录和虚拟环境的启动器。它不会打包 Python、依赖或模型；修改源码后，重启 app 即可运行更新后的代码。

```bash
scripts/build_macos_app.sh --install
```

## 构建发布安装包

发布用 DMG 通过 PyInstaller 构建独立 `.app`，输出到 `dist/release/`：

```bash
VIDEO_CAPTIONER_VERSION=macos-enhanced-v0.1.1 scripts/build_macos_release.sh
```

构建产物会包含 Python 运行时和 Python 依赖，但仍依赖系统可用的 FFmpeg，并会在首次使用 ASR 时下载模型。

## 支持格式

| 类型 | 格式 |
| --- | --- |
| 视频 | MP4、MKV、MOV、AVI、WebM、WMV、FLV、TS 等 |
| 音频 | MP3、WAV、AAC、FLAC、OGG、OPUS、M4A、WMA 等 |
| 字幕 | SRT、VTT、JSON、TXT |

## 上游与许可

原项目由 [@WEIFENG2333](https://github.com/WEIFENG2333) 创建。本分支基于原项目继续修改，许可证遵循原项目的 GPL-3.0 条款；如果对外发布 fork，请保留原项目版权和许可证信息。

## Codex 自动字幕工作流

新增本地 MCP + Skill 接入：提供视频链接，由本地 MLX Whisper 转录、当前 Codex 校对断句与翻译；按视频名建立任务目录，输出最终视频、原文/中文字幕、原文文稿及模板简介。最高画质下载遇到 VP9/AV1 时自动转为 HEVC，无需电脑操控或独立翻译 API。支持任务恢复和局部重转录。安装与使用见 [Codex MCP 指南](docs/codex-mcp.md)。

下载核心参考了 [FluentYTDL](https://github.com/SakuraForgot/FluentYTDL) 的生产经验：让 yt-dlp 使用其默认 YouTube 客户端策略、并行分片保持完整重试预算、认证失败分级恢复、403 过期断点清理，以及 Cookie 候选通过校验后再原子替换。这些规则由下载中心、预览解析、MCP 和兼容线程共同使用。
