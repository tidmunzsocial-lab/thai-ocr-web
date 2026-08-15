#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
  export OLLAMA_EXE="/Applications/Ollama.app/Contents/Resources/ollama"
elif command -v ollama >/dev/null 2>&1; then
  export OLLAMA_EXE="$(command -v ollama)"
fi

exec "$ROOT/.venv/bin/python" "$ROOT/web_app.py"
