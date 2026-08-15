import base64
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from typhoon_worker import PROMPT


MODEL = "scb10x/typhoon-ocr1.5-3b"
API = "http://127.0.0.1:11434"


def request(path: str, data: dict | None = None, timeout: int = 600) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = Request(API + path, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def ensure_server(ollama_exe: Path) -> None:
    try:
        request("/api/version", timeout=3)
        return
    except (OSError, URLError):
        subprocess.Popen(
            [str(ollama_exe), "serve"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    for _ in range(60):
        try:
            request("/api/version", timeout=3)
            return
        except (OSError, URLError):
            time.sleep(1)
    raise RuntimeError("Ollama เริ่มทำงานไม่สำเร็จ")


def main() -> None:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    ollama_exe = Path(sys.argv[2])
    ensure_server(ollama_exe)
    for item in manifest:
        image = base64.b64encode(Path(item["image"]).read_bytes()).decode()
        response = request("/api/chat", {
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT, "images": [image]}],
            "stream": False,
            "keep_alive": "2m",
            "options": {"temperature": 0, "num_ctx": 8192},
        })
        print("@@RESULT@@" + json.dumps({
            "page": item["page"],
            "text": response["message"]["content"].strip(),
            "boxed": item["image"],
        }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
