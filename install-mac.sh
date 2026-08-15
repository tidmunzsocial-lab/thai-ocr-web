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
if (( AVAILABLE_KB < 6291456 )); then
  echo "At least 6 GB of free disk space is required."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "[1/5] Installing web application..."
mkdir -p "$ROOT/.tools"
if [[ ! -x "$ROOT/.tools/uv" ]]; then
  curl -LsSf https://astral.sh/uv/0.11.32/install.sh | env UV_UNMANAGED_INSTALL="$ROOT/.tools" sh
fi
"$ROOT/.tools/uv" venv --python 3.12 "$ROOT/.venv"
"$ROOT/.tools/uv" pip install --python "$ROOT/.venv/bin/python" -r "$ROOT/requirements-mac.txt"

echo "[2/5] Installing PaddleOCR CPU..."
"$ROOT/.tools/uv" venv --python 3.12 --seed "$ROOT/.venv-paddle"
"$ROOT/.venv-paddle/bin/python" -m pip install paddleocr==3.3.2
"$ROOT/.venv-paddle/bin/python" -m pip install paddlepaddle==3.3.0 \
  --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/

echo "[3/5] Downloading lightweight Thai PaddleOCR models..."
DISABLE_MODEL_SOURCE_CHECK=True "$ROOT/.venv-paddle/bin/python" "$ROOT/paddle_worker.py" --download

echo "[4/5] Installing optional Typhoon Fast support..."
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

echo "[5/5] Creating launcher..."
chmod +x "$ROOT/Open-Thai-OCR-Web.command"
DESKTOP_DIR="$HOME/Desktop"
if [[ -d "$DESKTOP_DIR" && ! -e "$DESKTOP_DIR/Thai OCR Web.command" ]]; then
  ln -s "$ROOT/Open-Thai-OCR-Web.command" "$DESKTOP_DIR/Thai OCR Web.command"
fi

echo "Installation complete. Opening Thai OCR Web..."
open "$ROOT/Open-Thai-OCR-Web.command"
