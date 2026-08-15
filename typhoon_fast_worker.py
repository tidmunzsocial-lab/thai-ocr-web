import base64
import json
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from PIL import Image

from ocr_prompt import PROMPT


MODEL = "scb10x/typhoon-ocr1.5-3b"
API = "http://127.0.0.1:11434"


def runtime_settings(platform: str = sys.platform) -> tuple[int, int | None, str]:
    return (4096, 1600, "30s") if platform == "darwin" else (8192, None, "2m")


def encode_image(path: Path, max_size: int | None) -> str:
    if max_size is None:
        return base64.b64encode(path.read_bytes()).decode()
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode()


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
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
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
    num_ctx, max_image_size, keep_alive = runtime_settings()
    for item in manifest:
        image = encode_image(Path(item["image"]), max_image_size)
        response = request("/api/chat", {
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT, "images": [image]}],
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"temperature": 0, "num_ctx": num_ctx},
        })
        print("@@RESULT@@" + json.dumps({
            "page": item["page"],
            "text": response["message"]["content"].strip(),
            "boxed": item["image"],
        }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
