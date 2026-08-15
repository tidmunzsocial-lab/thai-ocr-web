from __future__ import annotations

import argparse
import gc
from html import escape
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import gradio as gr
import fitz

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "Unlimited-OCR"
TYPHOON_MODEL_PATH = ROOT / "models" / "Typhoon-OCR-1.5-2B"
OUTPUT_ROOT = ROOT / "outputs" / "web"


def find_ollama() -> Path:
    configured = os.environ.get("OLLAMA_EXE")
    candidates = [
        Path(configured) if configured else None,
        Path(shutil.which("ollama")) if shutil.which("ollama") else None,
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if os.name == "nt" else None,
        Path.home() / "Applications" / "Ollama.app" / "Contents" / "Resources" / "ollama",
        Path("/Applications/Ollama.app/Contents/Resources/ollama"),
    ]
    return next((path for path in candidates if path and path.is_file()), ROOT / "ollama-not-found")


OLLAMA_EXE = find_ollama()
PYTHON_EXE = Path(sys.executable)
PADDLE_PYTHON = ROOT / ".venv-paddle" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PADDLE_MODEL_PATHS = [
    Path.home() / ".paddlex" / "official_models" / "PP-OCRv5_mobile_det",
    Path.home() / ".paddlex" / "official_models" / "th_PP-OCRv5_mobile_rec",
]

_model = None
_tokenizer = None
_model_lock = threading.Lock()
_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_active_job_id: str | None = None
_active_process: subprocess.Popen | None = None
_cancel_event = threading.Event()
_model_admin_busy = False


def unload_fast_model() -> None:
    if OLLAMA_EXE.exists():
        subprocess.run(
            [str(OLLAMA_EXE), "stop", "scb10x/typhoon-ocr1.5-3b"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )


def _set_model_admin_busy(busy: bool) -> None:
    global _model_admin_busy
    with _jobs_lock:
        if busy:
            has_jobs = any(job["status"] in {"รอคิว", "กำลังทำ", "กำลังหยุด"} for job in _jobs.values())
            if has_jobs or _model_admin_busy:
                raise gr.Error("มีงานกำลังทำหรือจัดการโมเดลอยู่ กรุณารอให้เสร็จก่อน")
        _model_admin_busy = busy


def _fast_model_info() -> dict | None:
    if not OLLAMA_EXE.exists():
        raise RuntimeError("ไม่พบ Ollama")
    from typhoon_fast_worker import MODEL, ensure_server, request

    ensure_server(OLLAMA_EXE)
    models = request("/api/tags", timeout=10).get("models", [])
    return next((model for model in models if model.get("name", "").split(":", 1)[0] == MODEL), None)


def fast_model_status() -> str:
    try:
        model = _fast_model_info()
    except Exception as error:
        return f"⚠️ ตรวจสอบไม่ได้: {escape(str(error))}"
    if not model:
        return "🔴 ยังไม่ได้ติดตั้ง Typhoon Fast — กด **ติดตั้ง / อัปเดต** ก่อนใช้งาน"
    size_gb = model.get("size", 0) / 1024**3
    return f"🟢 Typhoon Fast ติดตั้งแล้ว • ใช้พื้นที่ {size_gb:.1f} GB"


def install_fast_model(progress=gr.Progress()) -> str:
    _set_model_admin_busy(True)
    try:
        if not OLLAMA_EXE.exists():
            raise gr.Error("ไม่พบ Ollama กรุณารันตัวติดตั้ง Mac อีกครั้ง")
        from typhoon_fast_worker import MODEL, ensure_server

        ensure_server(OLLAMA_EXE)
        progress(0, desc="กำลังดาวน์โหลด Typhoon Fast")
        result = subprocess.run(
            [str(OLLAMA_EXE), "pull", MODEL],
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if result.returncode:
            raise gr.Error("ติดตั้งโมเดลไม่สำเร็จ: " + (result.stderr or result.stdout)[-300:])
        progress(1, desc="ติดตั้งเสร็จแล้ว")
        return fast_model_status()
    finally:
        _set_model_admin_busy(False)


def _folder_size(paths: list[Path]) -> int:
    return sum(file.stat().st_size for path in paths if path.exists() for file in path.rglob("*") if file.is_file())


def _format_size(size: int) -> str:
    return f"{size / 1024**2:.0f} MB" if size < 1024**3 / 10 else f"{size / 1024**3:.1f} GB"


def installed_models_status() -> str:
    rows = []
    try:
        fast = _fast_model_info()
        rows.append(("Typhoon Fast (Ollama)", fast.get("size", 0) if fast else 0))
    except Exception:
        rows.append(("Typhoon Fast (Ollama)", 0))
    rows.extend([
        ("Typhoon ปกติ", _folder_size([TYPHOON_MODEL_PATH])),
        ("Unlimited-OCR", _folder_size([MODEL_PATH])),
        ("PaddleOCR ไทย", _folder_size(PADDLE_MODEL_PATHS)),
    ])
    return "\n".join(
        f"- 🟢 **{name}** — {_format_size(size)}" if size else f"- ⚪ **{name}** — ไม่ได้ติดตั้ง"
        for name, size in rows
        if sys.platform != "darwin" or name == "Typhoon Fast (Ollama)"
    )


def available_engines() -> list[str]:
    engines = []
    if all(path.exists() for path in PADDLE_MODEL_PATHS):
        engines.append("PaddleOCR (GPU/เร็ว)")
    if TYPHOON_MODEL_PATH.exists():
        engines.append("Typhoon OCR ปกติ (AI/ไทย)")
    try:
        if _fast_model_info():
            engines.append("Typhoon OCR Fast (AI/ไทย/เร็ว)")
    except Exception:
        pass
    if MODEL_PATH.exists():
        engines.append("Unlimited-OCR (AI/ละเอียด)")
    return engines


def _engine_dropdown(current: str | None):
    choices = available_engines()
    preferred = "Typhoon OCR Fast (AI/ไทย/เร็ว)"
    value = current if current in choices else preferred if preferred in choices else (choices[0] if choices else None)
    return gr.Dropdown(choices=choices, value=value)


def refresh_models_and_engine(current_engine: str):
    return installed_models_status(), _engine_dropdown(current_engine)


def install_fast_and_refresh(current_engine: str, progress=gr.Progress()):
    return install_fast_model(progress), _engine_dropdown(current_engine)


def remove_models_and_refresh(selected: list[str], confirmed: bool, current_engine: str):
    status, selected, confirmed = remove_selected_models(selected, confirmed)
    return status, selected, confirmed, _engine_dropdown(current_engine)


def remove_selected_models(selected: list[str], confirmed: bool):
    if not selected:
        raise gr.Error("กรุณาเลือกโมเดลที่ต้องการลบ")
    if not confirmed:
        raise gr.Error("กรุณาติ๊กยืนยันก่อนลบโมเดล")
    _set_model_admin_busy(True)
    try:
        paths = {
            "Typhoon ปกติ": [TYPHOON_MODEL_PATH],
            "Unlimited-OCR": [MODEL_PATH],
            "PaddleOCR ไทย": PADDLE_MODEL_PATHS,
        }
        removed = []
        for name in selected:
            if name == "Typhoon Fast (Ollama)":
                from typhoon_fast_worker import MODEL, ensure_server

                ensure_server(OLLAMA_EXE)
                unload_fast_model()
                result = subprocess.run(
                    [str(OLLAMA_EXE), "rm", MODEL], capture_output=True, text=True, timeout=120, check=False
                )
                if result.returncode and "not found" not in (result.stderr or result.stdout).lower():
                    raise gr.Error("ลบ Typhoon Fast ไม่สำเร็จ: " + (result.stderr or result.stdout)[-300:])
                removed.append(name)
                continue
            for path in paths.get(name, []):
                if path.exists():
                    shutil.rmtree(path)
            if name in paths:
                removed.append(name)
        return f"✅ ลบแล้ว: {', '.join(removed)}\n\n" + installed_models_status(), [], False
    finally:
        _set_model_admin_busy(False)


def open_output_folder() -> str:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(OUTPUT_ROOT)])
    elif os.name == "nt":
        os.startfile(OUTPUT_ROOT)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(OUTPUT_ROOT)])
    return f"📂 เปิดโฟลเดอร์ไฟล์งานบนเครื่องนี้แล้ว: `{OUTPUT_ROOT}`"


def clear_saved_jobs(confirmed: bool):
    if not confirmed:
        raise gr.Error("กรุณาติ๊กยืนยันก่อนล้างไฟล์งานทั้งหมด")
    with _jobs_lock:
        has_jobs = any(job["status"] in {"รอคิว", "กำลังทำ", "กำลังหยุด"} for job in _jobs.values())
        if has_jobs or _model_admin_busy:
            raise gr.Error("มีงานกำลังทำอยู่ กรุณารอให้เสร็จก่อน")

    output_root = OUTPUT_ROOT.resolve()
    if output_root != (ROOT / "outputs" / "web").resolve():
        raise RuntimeError("ตำแหน่งโฟลเดอร์ผลงานไม่ถูกต้อง")
    output_root.mkdir(parents=True, exist_ok=True)
    removed = 0
    for path in output_root.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed += 1
    with _jobs_lock:
        _jobs.clear()
    return f"✅ ล้างไฟล์งานเก่าแล้ว {removed} รายการ", False, jobs_panel()


def _update_job(job_id: str, **changes) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(changes)


def register_job(file_path: str | None, engine: str, page_spec: str):
    if not file_path:
        raise gr.Error("กรุณาเลือกไฟล์รูปหรือ PDF ก่อน")
    if not engine:
        raise gr.Error("ยังไม่มีโมเดล OCR กรุณาติดตั้งโมเดลก่อน")
    job_id = uuid.uuid4().hex[:8]
    with _jobs_lock:
        if _model_admin_busy:
            raise gr.Error("กำลังติดตั้งหรือลบโมเดล กรุณารอให้เสร็จก่อน")
        _jobs[job_id] = {
            "id": job_id,
            "document": Path(file_path).name,
            "engine": engine,
            "pages": page_spec,
            "status": "รอคิว",
            "phase": "รอเริ่มงาน",
            "done": 0,
            "total": 0,
            "created_at": time.time(),
        }
    return job_id, jobs_panel()


def _start_job(job_id: str) -> None:
    global _active_job_id
    _cancel_event.clear()
    with _jobs_lock:
        _active_job_id = job_id
        _jobs[job_id].update(status="กำลังทำ", phase="กำลังเตรียมเอกสาร", started_at=time.time())


def _finish_job(job_id: str, status: str, phase: str) -> None:
    global _active_job_id, _active_process
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(status=status, phase=phase, finished_at=time.time())
        if _active_job_id == job_id:
            _active_job_id = None
            _active_process = None
        finished = [key for key, job in _jobs.items() if job["status"] in {"เสร็จแล้ว", "หยุดแล้ว", "ผิดพลาด"}]
        for old_id in finished[:-10]:
            _jobs.pop(old_id, None)


def _set_active_process(process: subprocess.Popen | None) -> None:
    global _active_process
    with _jobs_lock:
        _active_process = process


def stop_current_job() -> str:
    with _jobs_lock:
        job_id = _active_job_id
        process = _active_process
        if job_id and job_id in _jobs:
            _jobs[job_id].update(status="กำลังหยุด", phase="กำลังหยุดงานปัจจุบัน")
    if not job_id:
        return jobs_panel()
    _cancel_event.set()
    if process and process.poll() is None:
        process.terminate()
    unload_fast_model()
    return jobs_panel()


def jobs_panel() -> str:
    with _jobs_lock:
        jobs = [dict(job) for job in _jobs.values()]
        active_id = _active_job_id
    active = next((job for job in jobs if job["id"] == active_id), None)
    queued = [job for job in jobs if job["status"] == "รอคิว"]
    recent = [job for job in jobs if job["status"] in {"เสร็จแล้ว", "หยุดแล้ว", "ผิดพลาด"}][-3:]
    if active:
        elapsed = int(time.time() - active.get("started_at", time.time()))
        current = f"{active['done']}/{active['total']} หน้า" if active["total"] else active["phase"]
        active_html = (
            f"<b>🟠 กำลังทำงาน</b> • {escape(active['engine'])} • {escape(active['document'])} "
            f"• {escape(active['phase'])} • {current} • {elapsed // 60}:{elapsed % 60:02d}"
        )
    else:
        active_html = "<b>🟢 เครื่องว่าง</b>"
    queue_html = "<br>".join(
        f"{index}. {escape(job['engine'])} • {escape(job['document'])} • หน้า {escape(str(job['pages']))}"
        for index, job in enumerate(queued, 1)
    ) or "ไม่มีงานรอ"
    queue_details = (
        f'<details><summary style="cursor:pointer">คิวที่รอ ({len(queued)} งาน)</summary>'
        f'<div style="padding:6px 0 0 18px">{queue_html}</div></details>'
        if queued else "คิว 0"
    )
    recent_html = (
        f"ล่าสุด: {escape(recent[-1]['status'])} • {escape(recent[-1]['document'])}"
        if recent else ""
    )
    return (
        '<div style="padding:7px 10px;border:1px solid #d1d5db;border-radius:8px;'
        'font-size:13px;line-height:1.35;display:flex;gap:14px;align-items:center;flex-wrap:wrap">'
        f"<span>{active_html}</span><span>{queue_details}</span>"
        f'<span style="color:#6b7280">{recent_html}</span></div>'
    )


def queue_button_label() -> str:
    with _jobs_lock:
        job_count = sum(job["status"] in {"รอคิว", "กำลังทำ", "กำลังหยุด"} for job in _jobs.values())
    return "เริ่มทำงาน" if job_count == 0 else f"เพิ่มเป็นคิวที่ {job_count + 1}"


def queue_ui_state():
    return jobs_panel(), queue_button_label()


def load_model():
    global _model, _tokenizer
    import torch
    from transformers import AutoModel, AutoTokenizer

    with _model_lock:
        if _model is None:
            if not torch.cuda.is_available():
                raise RuntimeError("ไม่พบ CUDA GPU กรุณาตรวจสอบไดรเวอร์ NVIDIA")
            _tokenizer = AutoTokenizer.from_pretrained(
                MODEL_PATH, trust_remote_code=True, local_files_only=True
            )
            _model = AutoModel.from_pretrained(
                MODEL_PATH,
                trust_remote_code=True,
                local_files_only=True,
                use_safetensors=True,
                torch_dtype=torch.bfloat16,
            ).eval().cuda()
    return _model, _tokenizer


def unload_model() -> None:
    global _model, _tokenizer
    with _model_lock:
        had_model = _model is not None
        _model = None
        _tokenizer = None
        gc.collect()
        if had_model:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


def pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 180) -> list[str]:
    paths: list[str] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as document:
        if document.page_count == 0:
            raise gr.Error("PDF ไม่มีหน้าเอกสาร")
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for index, page in enumerate(document):
            path = output_dir / f"page_{index + 1:04d}.png"
            page.get_pixmap(matrix=matrix, alpha=False).save(path)
            paths.append(str(path))
    return paths


def page_setup(file_path: str | None):
    if not file_path or Path(file_path).suffix.lower() != ".pdf":
        return "1", 1, "เอกสาร 1 หน้า • จะอ่านหน้า 1", 1
    with fitz.open(file_path) as document:
        total = document.page_count
    return "1", total, f"PDF มี {total} หน้า • จะอ่านหน้า 1", 1


def parse_pages(spec: str, total: int) -> list[int]:
    if spec.strip().lower() in {"ทั้งหมด", "all"}:
        return list(range(1, total + 1))
    pages = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            if start > end:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    pages = sorted(page for page in pages if 1 <= page <= total)
    if not pages:
        raise ValueError("กรุณาระบุหน้า เช่น 1, 3-5 หรือ 10")
    return pages


def shift_page_range(spec: str, total: int, direction: int) -> str:
    pages = parse_pages(spec, total)
    count = len(pages)
    start = max(1, min(total - count + 1, (max(pages) + 1) if direction > 0 else (min(pages) - count)))
    end = min(total, start + count - 1)
    return str(start) if start == end else f"{start}-{end}"


def selection_summary(spec: str, total: int) -> str:
    try:
        pages = parse_pages(spec, total)
        return f"จะอ่าน {len(pages)} หน้า: {pages[0]}" + (f"–{pages[-1]}" if len(pages) > 1 else "")
    except (TypeError, ValueError):
        return "รูปแบบไม่ถูกต้อง — ใช้แบบ 1, 3-5 หรือ 10"


def set_batch_size(spec: str, total: int, count: int):
    start = parse_pages(spec, total)[0]
    end = min(total, start + count - 1)
    new_spec = str(start) if start == end else f"{start}-{end}"
    return new_spec, selection_summary(new_spec, total)


def move_selection(spec: str, total: int, direction: int):
    new_spec = shift_page_range(spec, total, direction)
    return new_spec, selection_summary(new_spec, total)


def select_all_pages(total: int):
    spec = str(1) if total == 1 else f"1-{total}"
    return spec, selection_summary(spec, total)


def progress_bar(percent: int, label: str) -> str:
    return f"""
    <div style="margin:8px 0 16px">
      <div style="display:flex;gap:10px;margin-bottom:6px">
        <span>{label}</span><strong>{percent}%</strong>
      </div>
      <div style="height:16px;background:#e5e7eb;border-radius:999px;overflow:hidden">
        <div style="width:{percent}%;height:100%;background:#ff6f00;transition:width .25s"></div>
      </div>
    </div>"""


def _run_ocr_impl(
    job_id: str,
    file_path: str | None,
    mode_label: str,
    page_spec: str,
    total_pages: int,
    engine: str,
    progress=gr.Progress(),
):
    if not file_path:
        raise gr.Error("กรุณาเลือกไฟล์รูปหรือ PDF ก่อน")

    job_dir = OUTPUT_ROOT / uuid.uuid4().hex[:12]
    job_dir.mkdir(parents=True, exist_ok=True)
    source = Path(file_path)
    saved_source = job_dir / ("input" + source.suffix.lower())
    shutil.copy2(source, saved_source)

    _update_job(job_id, phase="กำลังแปลงเอกสารเป็นภาพ")
    yield "", [], None, "กำลังเตรียมเอกสาร...", progress_bar(0, "กำลังเตรียมเอกสาร")
    is_pdf = saved_source.suffix.lower() == ".pdf"
    page_paths = pdf_to_images(saved_source, job_dir) if is_pdf else [str(saved_source)]
    try:
        pages = parse_pages(page_spec, min(total_pages, len(page_paths))) if is_pdf else [1]
    except (TypeError, ValueError) as error:
        raise gr.Error(str(error)) from error
    _update_job(job_id, total=len(pages), pages=page_spec, phase=f"กำลังโหลด {engine}")

    yield "", [], None, f"กำลังโหลด {engine}...", progress_bar(0, f"กำลังโหลด {engine}")
    if engine.startswith("Typhoon OCR"):
        unload_model()
        is_fast = "Fast" in engine
        if is_fast and not OLLAMA_EXE.exists():
            raise gr.Error("ยังไม่ได้ติดตั้ง Ollama สำหรับ Typhoon Fast")
        if not is_fast and not TYPHOON_MODEL_PATH.exists():
            raise gr.Error("ยังไม่ได้ติดตั้ง Typhoon OCR")
        if not is_fast:
            unload_fast_model()
        manifest = [
            {"page": page, "image": page_paths[page - 1]}
            for page in pages
        ]
        manifest_file = job_dir / "typhoon_worker_manifest.json"
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        worker_command = (
            [str(PYTHON_EXE), str(ROOT / "typhoon_fast_worker.py"), str(manifest_file), str(OLLAMA_EXE)]
            if is_fast else [
                str(PYTHON_EXE),
                str(ROOT / "typhoon_worker.py"),
                str(manifest_file),
                str(TYPHOON_MODEL_PATH),
                "1800",
            ]
        )
        process = subprocess.Popen(
            worker_command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
        )
        _set_active_process(process)
        _update_job(job_id, phase=f"กำลังอ่านหน้า {pages[0]}")
        page_results, preview_files, log_tail = [], [], []
        for line in process.stdout or []:
            if not line.startswith("@@RESULT@@"):
                log_tail = (log_tail + [line.strip()])[-20:]
                continue
            data = json.loads(line.removeprefix("@@RESULT@@"))
            page_results.append(f"## หน้า {data['page']}\n\n{data['text']}")
            preview_files.append(data["boxed"])
            result_file = job_dir / "result.md"
            result_file.write_text("\n\n---\n\n".join(page_results), encoding="utf-8")
            done = len(page_results)
            percent = round(done / len(pages) * 100)
            next_page = pages[done] if done < len(pages) else None
            _update_job(job_id, done=done, phase=f"กำลังอ่านหน้า {next_page}" if next_page else "อ่านครบแล้ว")
            progress((done, len(pages)), desc=f"เสร็จหน้า {data['page']} ({done}/{len(pages)})")
            yield result_file.read_text(encoding="utf-8"), preview_files, str(result_file), f"เสร็จหน้า {data['page']} — {done}/{len(pages)} หน้า", progress_bar(percent, f"เสร็จแล้ว {done}/{len(pages)} หน้า")
        return_code = process.wait()
        _set_active_process(None)
        if _cancel_event.is_set():
            return
        if return_code != 0:
            raise gr.Error(f"{engine} ทำงานไม่สำเร็จ: " + " | ".join(log_tail[-3:]))
        return

    if engine.startswith("PaddleOCR"):
        unload_fast_model()
        unload_model()
        manifest = [
            {
                "page": page,
                "image": page_paths[page - 1],
                "output": str(job_dir / f"paddle_page_{page:04d}.jpg"),
            }
            for page in pages
        ]
        manifest_file = job_dir / "paddle_worker_manifest.json"
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        process = subprocess.Popen(
            [str(PADDLE_PYTHON), str(ROOT / "paddle_worker.py"), str(manifest_file)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "DISABLE_MODEL_SOURCE_CHECK": "True"},
        )
        _set_active_process(process)
        _update_job(job_id, phase=f"กำลังอ่านหน้า {pages[0]}")
        page_results, boxes_files, log_tail = [], [], []
        for line in process.stdout or []:
            if not line.startswith("@@RESULT@@"):
                log_tail = (log_tail + [line.strip()])[-20:]
                continue
            data = json.loads(line.removeprefix("@@RESULT@@"))
            page_results.append(f"## หน้า {data['page']}\n\n{data['text']}")
            boxes_files.append(data["boxed"])
            result_file = job_dir / "result.md"
            result_file.write_text("\n\n---\n\n".join(page_results), encoding="utf-8")
            done = len(page_results)
            percent = round(done / len(pages) * 100)
            next_page = pages[done] if done < len(pages) else None
            _update_job(
                job_id,
                done=done,
                phase=f"กำลังอ่านหน้า {next_page}" if next_page else "อ่านครบแล้ว",
            )
            progress((done, len(pages)), desc=f"เสร็จหน้า {data['page']} ({done}/{len(pages)})")
            yield result_file.read_text(encoding="utf-8"), boxes_files, str(result_file), f"เสร็จหน้า {data['page']} — {done}/{len(pages)} หน้า", progress_bar(percent, f"เสร็จแล้ว {done}/{len(pages)} หน้า")
        return_code = process.wait()
        _set_active_process(None)
        if _cancel_event.is_set():
            result_file = job_dir / "result.md"
            yield "\n\n---\n\n".join(page_results), boxes_files, str(result_file) if result_file.exists() else None, "หยุดงานแล้ว", progress_bar(round(len(page_results) / len(pages) * 100), "หยุดงานแล้ว")
            return
        if return_code != 0:
            raise gr.Error(f"{engine} ทำงานไม่สำเร็จ: " + " | ".join(log_tail[-3:]))
        return

    unload_fast_model()
    _update_job(job_id, phase=f"กำลังโหลด {engine}")
    model, tokenizer = load_model()
    import torch
    with _model_lock, torch.inference_mode():
        if is_pdf:
            page_results = []
            is_gundam = mode_label.startswith("เร็ว")
            boxes_files = []
            for position, page_number in enumerate(pages, start=1):
                if _cancel_event.is_set():
                    yield "\n\n---\n\n".join(page_results), [str(path) for path in boxes_files], None, "หยุดงานแล้ว", progress_bar(round((position - 1) / len(pages) * 100), "หยุดงานแล้ว")
                    return
                _update_job(job_id, phase=f"กำลังอ่านหน้า {page_number}", done=position - 1)
                progress((position - 1, len(pages)), desc=f"กำลังอ่านหน้า {page_number} ({position}/{len(pages)})")
                page_dir = job_dir / f"page_{page_number:04d}"
                model.infer(
                    tokenizer,
                    prompt="<image>document parsing.",
                    image_file=page_paths[page_number - 1],
                    output_path=str(page_dir),
                    base_size=1024,
                    image_size=640 if is_gundam else 1024,
                    crop_mode=is_gundam,
                    max_length=32768,
                    no_repeat_ngram_size=35,
                    ngram_window=128,
                    save_results=True,
                )
                page_result = page_dir / "result.md"
                if page_result.exists():
                    page_results.append(f"## หน้า {page_number}\n\n{page_result.read_text(encoding='utf-8')}")
                torch.cuda.empty_cache()
                result_file = job_dir / "result.md"
                result_file.write_text("\n\n---\n\n".join(page_results), encoding="utf-8")
                boxes_files = sorted(job_dir.glob("**/result_with_boxes.jpg"))
                percent = round(position / len(pages) * 100)
                _update_job(job_id, done=position, phase="อ่านครบแล้ว" if position == len(pages) else f"กำลังอ่านหน้า {pages[position]}")
                yield result_file.read_text(encoding="utf-8"), [str(path) for path in boxes_files], str(result_file), f"เสร็จหน้า {page_number} — {position}/{len(pages)} หน้า", progress_bar(percent, f"เสร็จแล้ว {position}/{len(pages)} หน้า")
            progress(1, desc="เสร็จแล้ว")
        else:
            is_gundam = mode_label.startswith("เร็ว")
            _update_job(job_id, phase="กำลังอ่านหน้า 1", total=1)
            model.infer(
                tokenizer,
                prompt="<image>document parsing.",
                image_file=str(saved_source),
                output_path=str(job_dir),
                base_size=1024,
                image_size=640 if is_gundam else 1024,
                crop_mode=is_gundam,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=128,
                save_results=True,
            )
            result_file = job_dir / "result.md"
            boxes_files = sorted(job_dir.glob("**/result_with_boxes.jpg"))
            text = result_file.read_text(encoding="utf-8") if result_file.exists() else "ไม่พบข้อความ"
            _update_job(job_id, done=1, phase="อ่านครบแล้ว")
            yield text, [str(path) for path in boxes_files], str(result_file), "เสร็จแล้ว 1/1 หน้า", progress_bar(100, "เสร็จแล้ว 1/1 หน้า")


def run_ocr(job_id: str, *args):
    _start_job(job_id)
    final_status, final_phase = "เสร็จแล้ว", "เสร็จแล้ว"
    try:
        yield from _run_ocr_impl(job_id, *args)
        if _cancel_event.is_set():
            final_status = final_phase = "หยุดแล้ว"
    except GeneratorExit:
        _cancel_event.set()
        with _jobs_lock:
            process = _active_process
        if process and process.poll() is None:
            process.terminate()
        final_status = final_phase = "หยุดแล้ว"
        raise
    except Exception as error:
        final_status, final_phase = "ผิดพลาด", str(error)[:160]
        raise
    finally:
        _finish_job(job_id, final_status, final_phase)


def build_app() -> gr.Blocks:
    is_mac = sys.platform == "darwin"
    with gr.Blocks(title="Unlimited OCR") as app:
        gr.Markdown(
            "# อ่านเอกสารจากรูปภาพหรือ PDF\n"
            "เลือกไฟล์ JPG/PNG/PDF แล้วกด **เริ่มอ่านเอกสาร** — PDF หลายหน้าอาจใช้เวลานาน"
        )
        jobs_display = gr.HTML(jobs_panel())
        jobs_timer = gr.Timer(1)
        with gr.Row():
            with gr.Column():
                document = gr.File(
                    type="filepath",
                    file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                    label="1. เลือกรูปหรือ PDF",
                )
                if is_mac:
                    mode = gr.State("เร็ว (แนะนำ)")
                    engine = gr.State("Typhoon OCR Fast (AI/ไทย/เร็ว)")
                    gr.Markdown("**OCR:** Typhoon Fast (ประหยัดพื้นที่สำหรับ Mac)")
                else:
                    engines = available_engines()
                    preferred_engine = "Typhoon OCR Fast (AI/ไทย/เร็ว)"
                    mode = gr.Radio(
                        ["เร็ว (แนะนำ)", "ละเอียดสูง"],
                        value="เร็ว (แนะนำ)",
                        label="คุณภาพ",
                    )
                    engine = gr.Dropdown(
                        engines,
                        value=preferred_engine if preferred_engine in engines else (engines[0] if engines else None),
                        label="OCR ที่ต้องการใช้",
                    )
                page_count = gr.State(1)
                page_spec = gr.State("1")
                batch_size = gr.Radio(
                    [("1 หน้า", 1), ("5 หน้า", 5), ("10 หน้า", 10)],
                    value=1,
                    label="อ่านครั้งละ",
                )
                page_info = gr.Markdown("เอกสาร 1 หน้า • จะอ่านหน้า 1")
                with gr.Row():
                    previous_button = gr.Button("← ชุดก่อนหน้า")
                    next_button = gr.Button("ชุดถัดไป →")
                    all_button = gr.Button("ทุกหน้า", variant="secondary")
                with gr.Row():
                    run_button = gr.Button(queue_button_label(), variant="primary")
                    stop_button = gr.Button("หยุดงานปัจจุบัน", variant="stop")
                with gr.Accordion("⚙️ ตั้งค่าและพื้นที่จัดเก็บ", open=False):
                    gr.Markdown("**โมเดล OCR** — เลือกลบเฉพาะตัวที่ไม่ได้ใช้เพื่อคืนพื้นที่")
                    model_status = gr.Markdown("กดตรวจสอบเพื่อดูโมเดลและพื้นที่ที่ใช้อยู่")
                    removable_models = gr.CheckboxGroup(
                        ["Typhoon Fast (Ollama)"] if is_mac else [
                            "Typhoon Fast (Ollama)", "Typhoon ปกติ", "Unlimited-OCR", "PaddleOCR ไทย"
                        ],
                        label="โมเดลที่ต้องการลบ",
                    )
                    confirm_model_removal = gr.Checkbox(label="ยืนยันว่าต้องการลบโมเดลที่เลือก", value=False)
                    with gr.Row():
                        check_model_button = gr.Button("ตรวจสอบโมเดล", size="sm")
                        install_model_button = gr.Button("ติดตั้ง / อัปเดต Fast", size="sm")
                        remove_models_button = gr.Button("ลบโมเดลที่เลือก", variant="stop", size="sm")
                    gr.Markdown("**ไฟล์งานเก่า** — ลบรูปที่อัปโหลด ภาพแต่ละหน้า และไฟล์ผลลัพธ์ทั้งหมด")
                    clear_confirm = gr.Checkbox(label="ยืนยันว่าต้องการล้างไฟล์งานทั้งหมด", value=False)
                    clear_files_button = gr.Button("ล้างไฟล์งานทั้งหมด", variant="stop", size="sm")
                    storage_status = gr.Markdown()
            with gr.Column():
                status = gr.Markdown("พร้อมใช้งาน")
                progress_display = gr.HTML(progress_bar(0, "พร้อมใช้งาน"))
                result = gr.Markdown(label="ข้อความที่อ่านได้")
                boxed = gr.Gallery(label="ภาพเอกสาร/กรอบข้อความ", columns=1)
                download = gr.File(label="ดาวน์โหลดผลลัพธ์ (.md)")
                open_folder_button = gr.Button("📂 เปิดโฟลเดอร์ไฟล์งาน", size="sm")
        job_id = gr.State("")
        document.change(page_setup, inputs=document, outputs=[page_spec, page_count, page_info, batch_size])
        batch_size.change(set_batch_size, inputs=[page_spec, page_count, batch_size], outputs=[page_spec, page_info])
        previous_button.click(lambda spec, total: move_selection(spec, total, -1), inputs=[page_spec, page_count], outputs=[page_spec, page_info])
        next_button.click(lambda spec, total: move_selection(spec, total, 1), inputs=[page_spec, page_count], outputs=[page_spec, page_info])
        all_button.click(select_all_pages, inputs=page_count, outputs=[page_spec, page_info])
        if is_mac:
            check_model_button.click(installed_models_status, outputs=model_status, queue=False, show_progress="hidden")
            install_model_button.click(install_fast_model, outputs=model_status)
            remove_models_button.click(
                remove_selected_models,
                inputs=[removable_models, confirm_model_removal],
                outputs=[model_status, removable_models, confirm_model_removal],
            )
        else:
            check_model_button.click(
                refresh_models_and_engine,
                inputs=engine,
                outputs=[model_status, engine],
                queue=False,
                show_progress="hidden",
            )
            install_model_button.click(install_fast_and_refresh, inputs=engine, outputs=[model_status, engine])
            remove_models_button.click(
                remove_models_and_refresh,
                inputs=[removable_models, confirm_model_removal, engine],
                outputs=[model_status, removable_models, confirm_model_removal, engine],
            )
        clear_files_button.click(
            clear_saved_jobs,
            inputs=clear_confirm,
            outputs=[storage_status, clear_confirm, jobs_display],
            queue=False,
        )
        open_folder_button.click(open_output_folder, outputs=status, queue=False, show_progress="hidden")
        jobs_timer.tick(queue_ui_state, outputs=[jobs_display, run_button], queue=False, show_progress="hidden")
        stop_button.click(stop_current_job, outputs=jobs_display, queue=False, show_progress="hidden")
        submit = run_button.click(
            register_job,
            inputs=[document, engine, page_spec],
            outputs=[job_id, jobs_display],
            queue=False,
            show_progress="hidden",
        )
        submit.then(
            run_ocr,
            inputs=[job_id, document, mode, page_spec, page_count, engine],
            outputs=[result, boxed, download, status, progress_display],
            concurrency_limit=1,
            concurrency_id="ocr_queue",
        )
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    build_app().queue(default_concurrency_limit=1).launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=not args.no_browser,
        show_error=True,
    )
