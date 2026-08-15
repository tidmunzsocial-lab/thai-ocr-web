#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This installer requires an Apple Silicon Mac (M1 or newer)."
  read -r -p "Press Enter to close..."
  exit 1
fi

MAC_MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
if (( MAC_MAJOR < 14 )); then
  echo "This installer requires macOS 14 Sonoma or newer."
  read -r -p "Press Enter to close..."
  exit 1
fi

AVAILABLE_KB="$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
if (( AVAILABLE_KB < 12582912 )); then
  echo "At least 12 GB of free disk space is required."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "[1/4] Installing Python environment..."
mkdir -p "$ROOT/.tools"
if [[ ! -x "$ROOT/.tools/uv" ]]; then
  curl -LsSf https://astral.sh/uv/0.11.32/install.sh | env UV_UNMANAGED_INSTALL="$ROOT/.tools" sh
fi
"$ROOT/.tools/uv" venv --python 3.12 "$ROOT/.venv"
"$ROOT/.tools/uv" pip install --python "$ROOT/.venv/bin/python" -r "$ROOT/requirements-mac.txt"

echo "[2/4] Installing Ollama..."
if ! command -v ollama >/dev/null 2>&1 && [[ ! -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

OLLAMA_BIN="$(command -v ollama || true)"
if [[ -z "$OLLAMA_BIN" && -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
  OLLAMA_BIN="/Applications/Ollama.app/Contents/Resources/ollama"
fi
if [[ -z "$OLLAMA_BIN" ]]; then
  echo "Ollama installation did not complete. Install it from https://ollama.com/download/mac and run this installer again."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "[3/4] Downloading Typhoon OCR Fast model..."
if [[ -d "/Applications/Ollama.app" ]]; then
  open -a Ollama || true
fi
if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  "$OLLAMA_BIN" serve >"$ROOT/ollama.log" 2>&1 &
fi
for _ in {1..60}; do
  curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break
  sleep 1
done
"$OLLAMA_BIN" pull scb10x/typhoon-ocr1.5-3b

echo "[4/4] Creating launcher..."
chmod +x "$ROOT/Open-Thai-OCR-Web.command"
DESKTOP_DIR="$HOME/Desktop"
if [[ -d "$DESKTOP_DIR" && ! -e "$DESKTOP_DIR/Thai OCR Web.command" ]]; then
  ln -s "$ROOT/Open-Thai-OCR-Web.command" "$DESKTOP_DIR/Thai OCR Web.command"
fi

echo "Installation complete. Opening Thai OCR Web..."
open "$ROOT/Open-Thai-OCR-Web.command"
