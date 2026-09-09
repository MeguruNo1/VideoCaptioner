# Codex + VideoCaptioner

输入单个视频链接，在 Codex 中自动完成下载、本地 MLX Whisper 转录、校对、断句、翻译和字幕导出。无需打开应用窗口或使用电脑操控，没有独立翻译 API 调用。音频本地处理；字幕文本作为 MCP 工具结果进入 Codex 对话。

## 安装

在现有 Apple Silicon macOS 项目环境中运行：

```sh
.venv/bin/python -m pip install -r requirements-mcp.txt
.venv/bin/python scripts/install_codex_mcp.py --dry-run
.venv/bin/python scripts/install_codex_mcp.py
```

安装器使用当前 Python 解释器的绝对路径和固定启动脚本，在 Codex 中注册 `videocaptioner` stdio MCP，并安装 `videocaptioner` Skill。现有 Codex 配置会备份；同名的其他服务或未托管 Skill 不会被覆盖。首次安装后新建 Codex 任务或刷新 MCP 和 Skill。

也可手工执行 `codex mcp add videocaptioner -- /绝对路径/.venv/bin/python /绝对路径/scripts/videocaptioner_mcp.py`，再将 `skills/videocaptioner` 安装到 Codex 的 skills 目录。

## 使用

对 Codex 说：

> 使用 videocaptioner 处理 https://www.youtube.com/watch?v=…，英语翻译成简体中文，输出视频及中英文字幕。

默认下载最高可用视频画质；VP9/AV1 自动转为 HEVC，不额外压制硬字幕。输出原文 SRT、中文 SRT、最终视频、Codex 校订后的原文文稿及使用软件当前模板生成的简介文稿。支持 `source_language`、`target_language`、`output_dir`、本地 `model`、`format_selector`、`proxy_url`、`cookie_file`、`initial_prompt` 参数。`source_language=auto` 使用 MLX 自动识别。

每次 `start_job` 都读取软件界面保存的同一份 `settings.json`。代理、下载引擎策略、Cookie 自动刷新及浏览器、HEVC 预设、MLX 模型/VAD/阈值/分块/热词，以及字幕长度、术语提示和文本后处理开关会保存为任务快照。界面修改自动作用于之后的新任务；运行中的任务保留启动时快照，保证恢复后结果一致。显式空代理表示直连。模型必须已经在本机路径或 Hugging Face 缓存中；缺失时 `check_environment` 会提示，不会自动下载大模型。依赖沿用现有 `requirements-macos-whisperx.txt` 环境，但新工作流程不加载 WhisperX 或 Qt。

## 任务与恢复

默认产物目录为 `~/Movies/VideoCaptioner/<视频名>`，其中 `flow` 保存下载源文件、转录音频、任务参数、日志、MLX 原始输出、字幕数据及校验清单，`output` 只保存交付文件。注册表位于 `~/Library/Application Support/VideoCaptioner/mcp`，可通过 `VIDEOCAPTIONER_MCP_ROOT` 改变。自定义输出目录不影响通过任务注册表恢复；同名但不属于当前任务的目录会自动追加数字，避免覆盖。

`output` 文件名为：`【字幕】「视频名」原文.srt`、`【字幕】「视频名」译文.srt`、`「视频名」.<视频扩展名>`、`【视频文稿】「视频名」原文.txt`、`【简介】「视频名」.txt`、`原封面.png`、`生成封面.png`。

下载流程同时保存原始 YouTube 封面。字幕完成后，Codex 通过 `get_cover_source` 取得原图，使用内置 GPT 图像编辑将画布扩展为 4:3、把封面文字翻译为中文，并尽量保留原字体、构图和视觉风格。生成文件通过 `set_generated_cover` 校验 4:3 比例并登记；缺少任一封面时导出校验不会通过。

`start_job` 立即返回 ID。阶段依次为下载、提取音频、等待 MLX、转录、等待字幕处理和完成。使用 `get_job` 查询、`list_jobs` 找回任务、`cancel_job` 取消、`resume_job` 恢复。独立进程持有任务锁，MLX 工作以全局文件锁串行运行。网络中断保留 yt-dlp partial 文件；字幕逐批原子保存。关闭 MCP 连接不会主动终止工作进程；电脑关机或工作进程异常后，下一次查询会标记为可恢复中断。

Codex 关闭后不能继续执行文本翻译；重新打开任务后从已保存批次继续。MCP 不会自行唤醒 Codex 或调用外部翻译服务。

## 字幕接口

`get_caption_batch` 返回最多约 160 个词、前后各 25 个上下文词、术语表、批次 ID 和版本。`submit_caption_batch` 的每条字幕使用首尾词 ID（包含端点）、校订原文和译文；必须完整连续覆盖本批。起止时间由服务器读取词锚点计算。相同内容重复提交无副作用；过期版本的不同内容会被拒绝。

下载阶段会优先取得 YouTube 自动字幕并生成视频文稿，在 MLX 转录前从文稿中匹配维护对照表、提取本视频的候选专名并生成任务热词。命中的对照关系会作为批次 `glossary` 返回，候选词通过 `term_candidates` 返回，供 Codex 校订和翻译。默认对照表为 `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Note/Translate/对照.md`，也可通过 `Subtitle.TermGlossaryPath` 修改。Codex 确认并提交的新对应关系会原子追加到文件末尾的 `MCP 自动收录` 管理区，已有手工条目和章节不会被改写。

批次同时返回任务的字幕设置。启用“屏蔽原文脏话”“去除译文逗号”或“删除译文全角句号”后，服务端会在保存字幕时执行与界面流程相同的处理，Codex 提示与最终导出不会各自采用不同设置。
中文译文中的双引号会统一为 `「」`，单引号统一为 `『』`；英文单词内部的撇号保持原样。

`retranscribe_range` 将指定词范围扩展到完整受影响批次，用邻接时间锚点确定音频区间，再用 MLX 转录。受影响批次及词 ID 更换，译文失效；其他已完成批次保留。原始及局部转录分别存档。

`validate_job` 检查覆盖、空译文、非法时间和字幕重叠，结构错误会阻止 `export_job`。位于有效字幕内部的 MLX 零时长词作为警告供复核，若它导致字幕边界塌缩则仍阻止提交。阅读速度、长度和不确定听写同样列为警告。不能仅凭文本判断时间是否整体提前；MLX 原生时间戳仍需要实际抽查。再次修订后导出会原子更新 `output` 中同名字幕和文稿；字幕 JSON、术语表、检查报告及清单留在 `flow`。

软件字幕流程和 MCP 导出都会补齐相邻字幕之间不超过 500 毫秒的正间隙：前一条字幕延长到下一条开始时间。超过阈值的停顿、零间隙和重叠不会修改。

## 开发验证

```sh
.venv/bin/python -m pytest tests/test_mcp_workflow.py tests/test_mcp_protocol.py -q
```

协议测试启动真实 stdio MCP 子进程，执行初始化、工具发现及环境检查；业务测试覆盖字幕完整性、版本冲突、取消、恢复、局部重转录和导出。真实网络与 MLX 验收需要联网权限、缓存模型及可用视频链接。
