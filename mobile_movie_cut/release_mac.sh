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
APP_NAME="HADO Match Extractor"

echo "========================================"
echo "  HADO Match Extractor - macOS Release"
echo "  Version: $VERSION"
echo "========================================"
echo ""

# --- 1. Build .app ---
echo "[1/2] Building .app ..."
bash "$SCRIPT_DIR/build_app.sh"
echo ""

# --- 2. Create ZIP ---
echo "[2/2] Creating ZIP ..."
mkdir -p "$RELEASE_DIR"

cd "$SCRIPT_DIR/dist"
zip -r -q "$RELEASE_DIR/$ZIP_NAME" "$APP_NAME.app"
cd "$PROJECT_ROOT"

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
