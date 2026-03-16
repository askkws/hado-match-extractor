#!/bin/bash
# Build and package macOS release ZIP for HADO Match Extractor
# Usage: bash release_mac.sh <version>
# Example: bash release_mac.sh 1.0.0

set -e

VERSION="$1"
if [ -z "$VERSION" ]; then
    echo "Usage: bash release_mac.sh <version>"
    echo "Example: bash release_mac.sh 1.0.0"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RELEASE_DIR="$PROJECT_ROOT/releases"
ZIP_NAME="HADO-Match-Extractor-v${VERSION}-macOS.zip"
STAGE_DIR="$(mktemp -d)"
APP_DIR="$STAGE_DIR/HADO Match Extractor"

echo "========================================"
echo "  HADO Match Extractor - macOS Release"
echo "  Version: $VERSION"
echo "========================================"
echo ""

# --- 1. Build .app ---
echo "[1/3] Building .app ..."
bash "$SCRIPT_DIR/build_app.sh"
echo ""

# --- 2. Stage files ---
echo "[2/3] Staging release files ..."
mkdir -p "$APP_DIR"

# Copy .app bundle
cp -R "$PROJECT_ROOT/HADO Match Extractor.app" "$APP_DIR/"

# Copy mobile_movie_cut (only needed files)
DEST="$APP_DIR/mobile_movie_cut"
mkdir -p "$DEST/static" "$DEST/templates" "$DEST/ffmpeg"

# Python sources
for f in main.py app.py extractor.py hado_detector.py hadoworld_detector.py; do
    cp "$SCRIPT_DIR/$f" "$DEST/"
done
cp "$SCRIPT_DIR/requirements.txt" "$DEST/"

# Static / Templates
cp "$SCRIPT_DIR/static/"* "$DEST/static/"
cp "$SCRIPT_DIR/templates/"* "$DEST/templates/"

# AppIcon
if [ -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/AppIcon.icns" "$DEST/"
fi

# ffmpeg binaries (macOS only)
for f in ffmpeg ffprobe; do
    if [ -f "$SCRIPT_DIR/ffmpeg/$f" ]; then
        cp "$SCRIPT_DIR/ffmpeg/$f" "$DEST/ffmpeg/"
        chmod +x "$DEST/ffmpeg/$f"
    fi
done

echo "  Staged to: $APP_DIR"

# --- 3. Create ZIP ---
echo "[3/3] Creating ZIP ..."
mkdir -p "$RELEASE_DIR"
cd "$STAGE_DIR"
zip -r -q "$RELEASE_DIR/$ZIP_NAME" "HADO Match Extractor"
cd "$PROJECT_ROOT"

# Cleanup
rm -rf "$STAGE_DIR"

ZIP_SIZE=$(du -h "$RELEASE_DIR/$ZIP_NAME" | cut -f1)
echo ""
echo "========================================"
echo "  Release ZIP created!"
echo ""
echo "  $RELEASE_DIR/$ZIP_NAME ($ZIP_SIZE)"
echo ""
echo "  To publish:"
echo "  gh release create v$VERSION \\"
echo "    \"$RELEASE_DIR/$ZIP_NAME\" \\"
echo "    --title \"v$VERSION\" --notes \"Release v$VERSION\""
echo "========================================"
