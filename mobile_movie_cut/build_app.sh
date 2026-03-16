#!/bin/bash
# Build macOS .app bundle for HADO Match Extractor
# Usage: bash build_app.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
APP_NAME="HADO Match Extractor"
APP_PATH="$PROJECT_ROOT/$APP_NAME.app"

echo "Building $APP_NAME.app ..."

# Check ffmpeg binaries
if [ ! -f "$SCRIPT_DIR/ffmpeg/ffmpeg" ] && [ ! -f "$SCRIPT_DIR/ffmpeg/ffmpeg.arm64" ]; then
    echo "ERROR: ffmpeg/ffmpeg が見つかりません。"
    echo "ffmpeg/README.md を参照してバイナリを配置してください。"
    exit 1
fi
if [ ! -f "$SCRIPT_DIR/ffmpeg/ffprobe" ] && [ ! -f "$SCRIPT_DIR/ffmpeg/ffprobe.arm64" ]; then
    echo "ERROR: ffmpeg/ffprobe が見つかりません。"
    echo "ffmpeg/README.md を参照してバイナリを配置してください。"
    exit 1
fi
echo "ffmpeg found in ffmpeg/"

# Clean previous build
rm -rf "$APP_PATH"

# Create .app bundle structure
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

# --- App icon ---
if [ -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/AppIcon.icns" "$APP_PATH/Contents/Resources/AppIcon.icns"
fi

# --- Info.plist ---
cat > "$APP_PATH/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>HADO Match Extractor</string>
    <key>CFBundleDisplayName</key>
    <string>HADO Match Extractor</string>
    <key>CFBundleIdentifier</key>
    <string>com.hado.match-extractor</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# --- Launcher script ---
cat > "$APP_PATH/Contents/MacOS/launcher" << 'LAUNCHER'
#!/bin/bash
# HADO Match Extractor - macOS App Launcher

APP_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
PROJECT_DIR="$APP_DIR/mobile_movie_cut"

if [ ! -d "$PROJECT_DIR" ]; then
    osascript -e 'display dialog "エラー: mobile_movie_cut フォルダが見つかりません。\n.app と同じフォルダに mobile_movie_cut を配置してください。" buttons {"OK"} default button "OK" with icon stop with title "HADO Match Extractor"'
    exit 1
fi

cd "$PROJECT_DIR"

# Bundled ffmpeg takes priority, then Homebrew, then system
export PATH="$PROJECT_DIR/ffmpeg:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Log file for debugging startup failures
LOG="/tmp/hado_launcher.log"
echo "=== HADO Launcher $(date) ===" > "$LOG"

# Find an arm64-native python3: prefer Homebrew, then fall back to PATH
PYTHON3=""
for candidate in \
    /opt/homebrew/bin/python3 \
    /opt/homebrew/bin/python3.13 \
    /opt/homebrew/bin/python3.12 \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3.10; do
    if [ -x "$candidate" ]; then
        PYTHON3="$candidate"
        break
    fi
done
if [ -z "$PYTHON3" ]; then
    PYTHON3="$(which python3)"
fi
echo "PYTHON3=$PYTHON3" >> "$LOG"

# Create venv if it doesn't exist yet
VENV_DIR="$PROJECT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv..." >> "$LOG"
    "$PYTHON3" -m venv "$VENV_DIR" >> "$LOG" 2>&1
fi

# Install dependencies into the venv
"$VENV_DIR/bin/pip" install -q -r requirements.txt >> "$LOG" 2>&1

# Run the desktop app using the venv Python (blocks until window is closed)
"$VENV_DIR/bin/python" main.py >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    osascript -e "display dialog \"エラー: アプリの起動に失敗しました。\n\n詳細はログを確認: $LOG\" buttons {\"OK\"} default button \"OK\" with icon stop with title \"HADO Match Extractor\""
fi
LAUNCHER

# Make launcher executable
chmod +x "$APP_PATH/Contents/MacOS/launcher"

echo ""
echo "Done! Created: $APP_PATH"
echo ""
echo "使い方:"
echo "  \"$APP_NAME.app\" をダブルクリックして起動"
echo ""
