#!/bin/bash
set -euo pipefail

RELEASE_TAG="v1.2.0"
INSTALL_DIR="$HOME/Thai-OCR-Web"
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/thai-ocr-web.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT

echo "Thai OCR Web for Mac (Apple Silicon)"
echo "Downloading application..."
curl -fL --retry 3 \
  "https://github.com/tidmunzsocial-lab/thai-ocr-web/archive/refs/tags/${RELEASE_TAG}.zip" \
  -o "$STAGE_DIR/source.zip"
ditto -xk "$STAGE_DIR/source.zip" "$STAGE_DIR/source"

SOURCE_DIR="$STAGE_DIR/source/thai-ocr-web-${RELEASE_TAG#v}"
mkdir -p "$INSTALL_DIR"
ditto "$SOURCE_DIR" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/install-mac.sh" "$INSTALL_DIR/Open-Thai-OCR-Web.command"
exec "$INSTALL_DIR/install-mac.sh"
