view/  目录结构：用户界面 (UI) 模块 

下面是本软件的一个主要页面结构，方便开发者查看和修改。


```
├── main_window.py  ------------------  主窗口 (无侧边栏应用程序框架)
│   │
│   └── 
│       ├── home_interface.py -------- 单一工作台 (程序主界面，包含核心功能)
│       │   │
│       │   └── 包含以下子功能模块:
│       │       ├── download_center_interface.py - 下载中心窗口
│       │       ├── transcription_interface.py - 语音转录窗口
│       │       ├── subtitle_interface.py -------- 字幕优化窗口
│       │
│       └── setting_interface.py -------------- 设置窗口 (顶部按钮打开)
│
├── log_window.py -------------------- 日志窗口 (独立窗口，集成在 home_interface)

```
