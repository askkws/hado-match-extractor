#!/bin/bash
# Build macOS .app bundle for HADO Match Extractor (PyInstaller)
# The .app bundle is self-contained — no external folders needed.
# Usage: bash build_app.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="HADO Match Extractor"

echo "Building $APP_NAME.app ..."

# --- Check ffmpeg binaries ---
FFMPEG_BIN=""
FFPROBE_BIN=""
for f in ffmpeg ffmpeg.arm64; do
    if [ -f "$SCRIPT_DIR/ffmpeg/$f" ]; then
        FFMPEG_BIN="$SCRIPT_DIR/ffmpeg/$f"
        break
    fi
done
for f in ffprobe ffprobe.arm64; do
    if [ -f "$SCRIPT_DIR/ffmpeg/$f" ]; then
        FFPROBE_BIN="$SCRIPT_DIR/ffmpeg/$f"
        break
    fi
done

if [ -z "$FFMPEG_BIN" ]; then
    echo "ERROR: ffmpeg binary not found in ffmpeg/"
    echo "See ffmpeg/README.md for download instructions."
    exit 1
fi
if [ -z "$FFPROBE_BIN" ]; then
    echo "ERROR: ffprobe binary not found in ffmpeg/"
    echo "See ffmpeg/README.md for download instructions."
    exit 1
fi
echo "ffmpeg:  $FFMPEG_BIN"
echo "ffprobe: $FFPROBE_BIN"

# --- venv ---
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -q --no-cache-dir -r "$SCRIPT_DIR/requirements.txt"
echo "Done."
echo ""

# --- Clean previous build ---
rm -rf "$SCRIPT_DIR/dist" "$SCRIPT_DIR/build"

# --- Icon flag ---
ICON_FLAG=""
if [ -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    ICON_FLAG="--icon $SCRIPT_DIR/AppIcon.icns"
fi

# --- PyInstaller ---
# macOS: --windowed produces a .app bundle (self-contained directory)
# --onefile is not compatible with macOS .app bundles
echo "Running PyInstaller..."
"$VENV_DIR/bin/pyinstaller" \
    --noconfirm \
    --windowed \
    --name "$APP_NAME" \
    --add-data "templates:templates" \
    --add-data "static:static" \
    --add-data "app.py:." \
    --add-data "extractor.py:." \
    --add-data "hado_detector.py:." \
    --add-data "hadoworld_detector.py:." \
    --add-binary "$FFMPEG_BIN:ffmpeg" \
    --add-binary "$FFPROBE_BIN:ffmpeg" \
    $ICON_FLAG \
    --hidden-import uvicorn.logging \
    --hidden-import uvicorn.loops \
    --hidden-import uvicorn.loops.auto \
    --hidden-import uvicorn.protocols \
    --hidden-import uvicorn.protocols.http \
    --hidden-import uvicorn.protocols.http.auto \
    --hidden-import uvicorn.protocols.websockets \
    --hidden-import uvicorn.protocols.websockets.auto \
    --hidden-import uvicorn.lifespan \
    --hidden-import uvicorn.lifespan.on \
    --hidden-import cv2 \
    --workpath "$SCRIPT_DIR/build" \
    --distpath "$SCRIPT_DIR/dist" \
    --specpath "$SCRIPT_DIR" \
    "$SCRIPT_DIR/main.py"

echo ""
echo "========================================"
echo "  Build complete!"
echo ""
echo "  Output: $SCRIPT_DIR/dist/$APP_NAME.app"
echo "========================================"
