#!/usr/bin/env bash
set -euo pipefail

PROVIDER_VERSION="1.3.1"
APP_SUPPORT_DIR="${VIDEO_CAPTIONER_APP_SUPPORT_DIR:-$HOME/Library/Application Support/VideoCaptioner}"
TARGET_DIR="${VIDEO_CAPTIONER_POT_PROVIDER_DIR:-$APP_SUPPORT_DIR/youtube-pot-provider}"
TARGET_SCRIPT="$TARGET_DIR/server/build/generate_once.js"

if [[ -f "$TARGET_SCRIPT" && -d "$TARGET_DIR/server/node_modules" ]]; then
    current_version="$(node "$TARGET_SCRIPT" --version 2>/dev/null || true)"
    if [[ "$current_version" == "$PROVIDER_VERSION" ]]; then
        echo "YouTube PO Token provider $PROVIDER_VERSION is already installed."
        exit 0
    fi
fi

for command in git node npm; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Missing required command: $command" >&2
        echo "Install Node.js 20+ and Git, then run this script again." >&2
        exit 1
    fi
done

TEMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

echo "Downloading YouTube PO Token provider $PROVIDER_VERSION..."
git clone \
    --depth 1 \
    --branch "$PROVIDER_VERSION" \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    "$TEMP_DIR/provider"

(
    cd "$TEMP_DIR/provider/server"
    npm ci
    npx tsc
    npm prune --omit=dev
)

mkdir -p "$(dirname "$TARGET_DIR")"
BACKUP_DIR=""
if [[ -e "$TARGET_DIR" ]]; then
    BACKUP_DIR="$TARGET_DIR.backup.$(date +%Y%m%d%H%M%S)"
    mv "$TARGET_DIR" "$BACKUP_DIR"
fi

if ! mv "$TEMP_DIR/provider" "$TARGET_DIR"; then
    if [[ -n "$BACKUP_DIR" && -e "$BACKUP_DIR" ]]; then
        mv "$BACKUP_DIR" "$TARGET_DIR"
    fi
    exit 1
fi

if [[ -n "$BACKUP_DIR" && -e "$BACKUP_DIR" ]]; then
    rm -rf "$BACKUP_DIR"
fi

installed_version="$(node "$TARGET_SCRIPT" --version)"
if [[ "$installed_version" != "$PROVIDER_VERSION" ]]; then
    echo "Provider verification failed: expected $PROVIDER_VERSION, got $installed_version" >&2
    exit 1
fi

echo "Installed YouTube PO Token provider $installed_version at:"
echo "$TARGET_DIR"
