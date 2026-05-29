#!/usr/bin/env bash
set -euo pipefail

APP_NAME="VideoCaptioner"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
LAUNCHER_SOURCE="$DIST_DIR/${APP_NAME}Launcher.c"
ICON_SOURCE="$PROJECT_ROOT/resource/assets/logo.png"
ICONSET_DIR="$DIST_DIR/AppIcon.iconset"
ICON_FILE="$RESOURCES_DIR/AppIcon.icns"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"

rm -rf "$APP_DIR" "$ICONSET_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

generate_app_icon() {
    if [[ ! -f "$ICON_SOURCE" ]]; then
        echo "Missing app icon source: $ICON_SOURCE" >&2
        exit 1
    fi
    if ! command -v sips >/dev/null 2>&1; then
        echo "Missing required macOS icon tool: sips" >&2
        exit 1
    fi
    if [[ ! -x "$PYTHON_BIN" ]]; then
        PYTHON_BIN="$(command -v python3 || true)"
    fi
    if [[ -z "$PYTHON_BIN" ]]; then
        echo "Missing required Python runtime for app icon generation" >&2
        exit 1
    fi

    mkdir -p "$ICONSET_DIR"
    sips -z 16 16 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
    sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
    sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
    sips -z 64 64 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
    sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
    sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
    sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null
    "$PYTHON_BIN" - "$ICON_FILE" "$ICONSET_DIR" <<'PY'
import sys
from pathlib import Path

icon_file = Path(sys.argv[1])
iconset_dir = Path(sys.argv[2])
entries = [
    ("icp4", "icon_16x16.png"),
    ("icp5", "icon_32x32.png"),
    ("icp6", "icon_32x32@2x.png"),
    ("ic07", "icon_128x128.png"),
    ("ic08", "icon_256x256.png"),
    ("ic09", "icon_512x512.png"),
    ("ic10", "icon_512x512@2x.png"),
]

chunks = []
for icon_type, filename in entries:
    data = (iconset_dir / filename).read_bytes()
    chunks.append(
        icon_type.encode("ascii")
        + (len(data) + 8).to_bytes(4, "big")
        + data
    )

body = b"".join(chunks)
icon_file.write_bytes(b"icns" + (len(body) + 8).to_bytes(4, "big") + body)
PY
    rm -rf "$ICONSET_DIR"
}

generate_app_icon

cat > "$CONTENTS_DIR/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>zh_CN</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.videocaptioner.local</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.3.3-local</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

cat > "$LAUNCHER_SOURCE" <<LAUNCHER
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern char **environ;

static void fail(const char *message) {
    fprintf(stderr, "VideoCaptioner launcher: %s: %s\\n", message, strerror(errno));
    exit(1);
}

int main(void) {
    const char *project_root = "$PROJECT_ROOT";
    const char *python = "$PROJECT_ROOT/.venv/bin/python";
    const char *main_py = "$PROJECT_ROOT/main.py";
    const char *path_prefix = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin";
    const char *old_path = getenv("PATH");
    char path_env[4096];

    if (old_path && old_path[0] != '\\0') {
        snprintf(path_env, sizeof(path_env), "%s:%s", path_prefix, old_path);
    } else {
        snprintf(path_env, sizeof(path_env), "%s", path_prefix);
    }
    setenv("PATH", path_env, 1);

    if (chdir(project_root) != 0) {
        fail("failed to enter project directory");
    }

    char *const argv[] = {(char *)python, (char *)main_py, NULL};
    execve(python, argv, environ);
    fail("failed to start Python");
}
LAUNCHER

clang -arch arm64 -O2 "$LAUNCHER_SOURCE" -o "$MACOS_DIR/$APP_NAME"
chmod +x "$MACOS_DIR/$APP_NAME"

if [[ "${1:-}" == "--install" ]]; then
    rm -rf "/Applications/$APP_NAME.app"
    cp -R "$APP_DIR" "/Applications/$APP_NAME.app"
    echo "Installed /Applications/$APP_NAME.app"
else
    echo "Built $APP_DIR"
fi
