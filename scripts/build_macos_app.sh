#!/usr/bin/env bash
set -euo pipefail

APP_NAME="VideoCaptioner"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
LAUNCHER_SOURCE="$DIST_DIR/${APP_NAME}Launcher.c"

mkdir -p "$MACOS_DIR"
rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR"

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
