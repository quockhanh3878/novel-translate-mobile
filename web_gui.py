"""web_gui.py - GUI web toi thieu (chi http.server chuan lib, khong Flask/Tkinter) de
chay pipeline.py (cao -> dich DeepSeek API -> dong goi EPUB va PDF) tu trinh duyet dien thoai.

Chay: python web_gui.py roi mo http://localhost:8000
Giao dien nam trong thu muc web/ (index.html, app.css, app.js, fonts/).
Mac dinh chi nghe tren 127.0.0.1; dat NOVEL_GUI_HOST=0.0.0.0 neu muon mo cho may khac trong mang.
"""
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.parse
import tempfile
from pathlib import Path

import requests

from build_epub import build_epub
from build_pdf import build_pdf
from cost_estimate import estimate_catalog, estimate_file, usd_from_usage
from sources import find_adapter
from crawler import guess_title
from deepseek_translate import (load_dotenv, TRANSLATE_SYSTEM_PROMPT,
                                call_deepseek, translate_chapter,
                                DEFAULT_MODEL, DEFAULT_REASONING_EFFORT, REASONING_EFFORTS,
                                is_peak_hour)
from text_postprocess import postprocess
from version import __version__
from path_resolver import (sanitize_filename, validate_output_dir,
                           resolve_pipeline_paths, is_safe_path, safe_upload_file)

REGISTERED_OUTPUT_DIRS: set[Path] = set()

DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"

# Load env variables on startup
load_dotenv()

# --- Termux wake-lock: giu man hinh/CPU hoat dong khi dich ---
_IS_TERMUX = os.path.exists("/data/data/com.termux")


def _termux_wake_lock():
    """Bat wake-lock tren Termux de Android khong kill process khi tat man hinh."""
    if _IS_TERMUX:
        try:
            subprocess.run(["termux-wake-lock"], timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def _termux_wake_unlock():
    """Tat wake-lock khi pipeline ket thuc."""
    if _IS_TERMUX:
        try:
            subprocess.run(["termux-wake-unlock"], timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def _termux_notify(title: str, content: str) -> None:
    """Gui thong bao Android qua termux-notification khi chay tren Termux."""
    if _IS_TERMUX:
        try:
            subprocess.run(["termux-notification", "-t", str(title), "-c", str(content)],
                           timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def save_api_key(key):
    key = key.strip()
    if not key:
        return
    # Ghi hoac cap nhat file .env
    env_lines = []
    has_key = False
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("DEEPSEEK_API_KEY="):
                    env_lines.append(f"DEEPSEEK_API_KEY={key}\n")
                    has_key = True
                else:
                    env_lines.append(line)
    if not has_key:
        env_lines.append(f"DEEPSEEK_API_KEY={key}\n")
        
    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(env_lines)
        
    # Cap nhat vao os.environ de script dang chay nhan duoc luon
    os.environ["DEEPSEEK_API_KEY"] = key


def test_deepseek_key(key):
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "Hi"}],
        "thinking": {"type": "disabled"},
        "max_tokens": 5
    }
    try:
        resp = requests.post("https://api.deepseek.com/chat/completions", headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            return True, "Key hợp lệ! Kết nối thành công tới DeepSeek API."
        else:
            try:
                data = resp.json()
                err_msg = data.get("error", {}).get("message", resp.text)
            except Exception:
                err_msg = resp.text
            return False, f"Lỗi (Mã {resp.status_code}): {err_msg[:500]}"
    except Exception as e:
        return False, f"Lỗi kết nối: {e}"


def get_deepseek_balance(key=""):
    key = (key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        return {"available": False, "reason": "Chưa có API Key."}

    try:
        resp = requests.get(
            DEEPSEEK_BALANCE_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"available": False, "reason": f"Không lấy được số dư (mã {resp.status_code})."}
        data = resp.json()
        if not isinstance(data, dict):
            return {"available": False, "reason": "DeepSeek trả về dữ liệu số dư không hợp lệ."}
        infos = data.get("balance_infos")
        if not isinstance(infos, list):
            return {"available": False, "reason": "DeepSeek trả về dữ liệu số dư không hợp lệ."}
        safe_infos = []
        for info in infos:
            if not isinstance(info, dict):
                continue
            safe_infos.append({
                "currency": str(info.get("currency", "")),
                "total_balance": str(info.get("total_balance", "0")),
                "granted_balance": str(info.get("granted_balance", "0")),
                "topped_up_balance": str(info.get("topped_up_balance", "0")),
            })
        return {
            "available": True,
            "is_available": bool(data.get("is_available")),
            "balance_infos": safe_infos,
        }
    except (requests.RequestException, ValueError) as exc:
        return {"available": False, "reason": f"Không kết nối được để lấy số dư: {exc}"}


def test_translate_handler(chinese_text: str, api_key: str) -> dict:
    """Dich doan van Trung -> Viet va xuat EPUB/PDF de kiem tra pipeline."""
    global TEST_EPUB_PATH, TEST_PDF_PATH
    try:
        system_prompt = TRANSLATE_SYSTEM_PROMPT.format(
            style_guide_block="",
            term_categories="các thuật ngữ đặc thù của truyện, thành ngữ, tục ngữ",
            glossary_block="")
        chapter = {"title": "Chuong thu nhat", "paragraphs": [chinese_text]}
        # Dich thu 1 doan: khong co truyen nao nen glossary rong (van bat goi y thanh ngu).
        translated = translate_chapter(chapter, system_prompt, api_key,
                                       model=DEFAULT_MODEL, temperature=1.3,
                                       thinking=True, glossary={},
                                       reasoning_effort=DEFAULT_REASONING_EFFORT)

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                          encoding="utf-8")
        try:
            tmp.write(f"=== {translated['title']} ===\n\n")
            for p in translated["paragraphs"]:
                tmp.write(f"{p}\n\n")
            tmp.write("=" * 40 + "\n")
            tmp.close()

            if TEST_EPUB_PATH and os.path.exists(TEST_EPUB_PATH):
                os.remove(TEST_EPUB_PATH)
            if TEST_PDF_PATH and os.path.exists(TEST_PDF_PATH):
                os.remove(TEST_PDF_PATH)

            epub_file = TEST_EPUB_NAME
            pdf_file = TEST_PDF_NAME
            build_epub(tmp.name, epub_file, "Truyen dung thu", "DeepSeek API")
            build_pdf(tmp.name, pdf_file, "Truyen dung thu", "DeepSeek API")
            TEST_EPUB_PATH = os.path.abspath(epub_file)
            TEST_PDF_PATH = os.path.abspath(pdf_file)

            return {
                "success": True,
                "translated_text": "\n".join(translated["paragraphs"]),
                "epub_file": epub_file,
                "pdf_file": pdf_file,
            }
        finally:
            os.unlink(tmp.name)

    except Exception as e:
        return {"success": False, "message": f"Loi dich thu: {e}", "detail": traceback.format_exc()}


# Trạng thái toàn cục để web cap nhat realtime
STATE = {
    "running": False,
    "log": "",
    "epub": None,
    "pdf": None,
    "error": None,
    "step": "idle",          # "idle", "crawling", "translating", "packaging", "done"
    "current_chapter": 0,
    "total_chapters": 0,
    "stop_requested": False,  # dat truoc khi CURRENT_PROC ton tai van phai duoc ton trong
    "error_detail": "",       # traceback/duoi log day du de nguoi dung copy di fix
    "raw_file": "",           # file tho dang dung cho lan chay hien tai (de ro rang)
    "translated_file": "",
    "cost_spent": 0.0,
    "cost_model": DEFAULT_MODEL,
    "allow_peak": False,
}
LOCK = threading.Lock()
CURRENT_PROC = None
TEST_EPUB_PATH = None  # duong dan file EPUB dung thu vua tao
TEST_EPUB_NAME = "test_dung_thu.epub"
TEST_PDF_PATH = None  # duong dan file PDF dung thu vua tao
TEST_PDF_NAME = "test_dung_thu.pdf"
UPLOAD_DIR = "uploads"  # noi luu file da cao nguoi dung chon tu may

WEB_DIR = Path(__file__).resolve().parent / "web"
ASSET_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
}
# Launcher (.exe) gan ham tat server vao day de nut "Thoat ung dung" hoat dong.
SHUTDOWN_HOOK = None


def _web_file(rel: str):
    """Duong dan file tren giao dien trong web/, hoac None neu khong hop le (chong ../)."""
    try:
        path = (WEB_DIR / rel).resolve()
        path.relative_to(WEB_DIR.resolve())
    except (ValueError, OSError):
        return None
    if path.suffix.lower() not in ASSET_TYPES and path.name != "index.html":
        return None
    return path if path.is_file() else None


# Thu muc Documents chung tren Android Termux de app doc sach de dang quet thay
SHARED_DOCUMENTS = os.path.expanduser("~/storage/shared/Documents")


def _export_to_android_storage(file_path: str) -> str | None:
    """Sao chep file EPUB/PDF sang thu muc Documents/Download tren Android."""
    if not os.path.isfile(file_path):
        return None

    candidates = [
        SHARED_DOCUMENTS,
        os.path.expanduser("~/storage/shared/Download"),
        os.path.expanduser("~/storage/downloads"),
        "/sdcard/Documents",
        "/sdcard/Download",
    ]
    filename = os.path.basename(file_path)
    for folder in candidates:
        try:
            folder_path = Path(folder)
            parent = folder_path.parent
            if parent.is_dir() or folder_path.is_dir():
                folder_path.mkdir(parents=True, exist_ok=True)
                dest = folder_path / filename
                shutil.copy2(file_path, str(dest))
                return str(dest)
        except Exception:
            continue
    return None

def force_kill_after_grace(proc, grace=5):
    """terminate() (SIGTERM) thuong du, nhung neu tien trinh khong thoat trong
    vai giay (vd ket noi mang treo o tang he dieu hanh) thi kill() (SIGKILL) de
    dam bao nut "Dung" luon co hieu luc."""
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return name or "truyen"


def resolve_raw_file(input_val: str, title: str = "") -> str:
    """Return the stable raw-file path for a URL or preserve an explicit file path.

    URL-derived names are canonical so changing the display title cannot start a
    second crawl. The title-derived path remains a compatibility fallback for
    files created by older GUI versions.
    """
    paths = resolve_pipeline_paths(input_val, title=title)
    return str(paths["raw_path"].name if paths["is_url"] else paths["raw_path"])


STEP_MARKER_RE = re.compile(r"=== Buoc (\d)/4:")
USAGE_LINE_RE = re.compile(
    r"prompt_tokens=(\d+).*?cache_hit=(\d+).*?cache_miss=(\d+).*?"
    r"completion_tokens=(\d+)")


def _worker_command():
    """Lenh chay pipeline trong tien trinh con. Ban .exe dong goi khong co pipeline.py roi,
    nen goi lai chinh file .exe voi --worker (launcher.py chuyen sang pipeline.main)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker"]
    return [sys.executable, "-u", "pipeline.py"]


def _worker_env():
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_pipeline(input_val, title, author="", model=DEFAULT_MODEL, workers=1, temperature=1.3, allow_peak=False, no_style_detect=False, no_thinking=False, stream_mode=False, chapters=0, reasoning_effort=DEFAULT_REASONING_EFFORT, output_dir=""):
    title = title or guess_title(input_val)
    # -u: khong buffer stdout cua tien trinh con - neu khong, print() trong
    # crawler.py/pipeline.py bi block-buffer (khong phai tty) nen log/tien do
    # tren GUI dung im (giong "treo") hang chuc chuong roi moi hien 1 luc.
    args = _worker_command() + ["--title", title]
    if author:
        args += ["--author", author]
    args += ["--model", model]
    args += ["--reasoning-effort", reasoning_effort]
    args += ["--workers", str(workers)]
    args += ["--temperature", str(temperature)]
    if allow_peak:
        args += ["--allow-peak"]
    if no_style_detect:
        args += ["--no-style-detect"]
    if no_thinking:
        args += ["--no-thinking"]
    if stream_mode:
        args += ["--stream"]
        if chapters > 0:
            args += ["--chapters", str(chapters)]

    paths = resolve_pipeline_paths(input_val, title=title, output_dir=output_dir)
    raw_file = str(paths["raw_path"])
    translated_file = str(paths["translated_path"])
    epub_file = str(paths["epub_path"])
    pdf_file = str(paths["pdf_path"])
    out_dir_str = str(paths["output_dir"])

    if paths["is_url"]:
        args += ["--start-url", input_val, "--raw", raw_file]
    else:
        args += ["--raw", raw_file]
    args += ["--translated", translated_file, "--epub", epub_file, "--pdf", pdf_file]

    global CURRENT_PROC
    with LOCK:
        STATE.update(
            running=True,
            log="",
            epub=None,
            pdf=None,
            error=None,
            error_detail="",
            step="streaming" if stream_mode else "crawling",
            current_chapter=0,
            total_chapters=chapters if stream_mode and chapters > 0 else 0,
            stop_requested=False,
            stream_mode=stream_mode,
            raw_file=raw_file,
            translated_file=translated_file,
            output_dir=out_dir_str,
            epub_path=epub_file,
            pdf_path=pdf_file,
            cost_spent=0.0,
            cost_model=model,
            allow_peak=allow_peak,
        )

    try:
        _termux_wake_lock()
        popen_kwargs = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                encoding="utf-8", errors="replace", env=_worker_env(), **popen_kwargs)
        with LOCK:
            CURRENT_PROC = proc
            # Nguoi dung co the bam "Dung" ngay trong khoang thoi gian ngan giua
            # luc STATE["running"] duoc dat True va luc proc/CURRENT_PROC ton tai
            # o tren - khong ton trong stop_requested o day se lam tien trinh
            # chay tiep du nguoi dung da bam dung (bug "dung khong duoc").
            if STATE["stop_requested"]:
                try:
                    proc.terminate()
                except Exception:
                    pass

        for line in proc.stdout:
                with LOCK:
                    STATE["log"] += line

                    usage_match = USAGE_LINE_RE.search(line)
                    if usage_match:
                        usage = {
                            "prompt_cache_hit_tokens": int(usage_match.group(2)),
                            "prompt_cache_miss_tokens": int(usage_match.group(3)),
                            "completion_tokens": int(usage_match.group(4)),
                        }
                        try:
                            usage_peak = bool(allow_peak and is_peak_hour())
                            STATE["cost_spent"] += usd_from_usage(
                                usage, model=model, peak=usage_peak)
                        except Exception:
                            pass
                
                # Parse steps: pipeline.py in "=== Buoc N/4: ..." (1 cao, 2 dich, 3 kiem tra, 4 dong goi).
                # Che do stream gop buoc 1-2 thanh "streaming" nen bo qua hai moc dau.
                step_match = STEP_MARKER_RE.search(line)
                if step_match:
                    marker = int(step_match.group(1))
                    if marker == 1 and not stream_mode:
                        STATE["step"] = "crawling"
                    elif marker == 2 and not stream_mode:
                        STATE["step"] = "translating"
                    elif marker == 3:
                        STATE["step"] = "validating"
                    elif marker == 4:
                        STATE["step"] = "packaging"
                
                # Parse crawl progress
                if STATE["step"] == "crawling":
                    crawl_match = re.search(r"(?:Da luu chuong|Da co)\s+(\d+)", line)
                    if crawl_match:
                        STATE["current_chapter"] = int(crawl_match.group(1))
                        
                # Parse total chapters to translate
                total_match = re.search(r"Da phan tich\s+(\d+)\s+chuong", line)
                if total_match:
                    STATE["total_chapters"] = int(total_match.group(1))
                    
                # Parse translation starting point (if resume)
                translated_pre_match = re.search(r"Da dich\s+(\d+)\s+chuong truoc do", line)
                if translated_pre_match:
                    STATE["current_chapter"] = int(translated_pre_match.group(1))
                    
                # Parse active translation progress
                progress_match = re.search(r"\[(\d+)/(\d+)\]", line)
                if progress_match:
                    STATE["current_chapter"] = int(progress_match.group(1))
                    STATE["total_chapters"] = int(progress_match.group(2))
                    
        proc.wait()
        
        with LOCK:
            STATE["running"] = False
            CURRENT_PROC = None

            # Dung theo yeu cau nguoi dung (nut "Dung", stop_requested da duoc
            # dat truoc do) - khong phai loi, khong can dinh kem error_detail.
            if STATE["stop_requested"]:
                STATE["error"] = "Da dung theo yeu cau."
                STATE["step"] = "idle"
                return

            if proc.returncode != 0:
                # Loi THUC SU (khong phai nguoi dung bam Dung) - dinh kem duoi
                # log (thuong chua traceback vi stderr da duoc gop vao stdout o
                # tren) de nguoi dung copy nguyen van di fix, khong phai doan mo.
                STATE["error"] = f"Loi (ma thoat {proc.returncode}), xem chi tiet ben duoi."
                STATE["error_detail"] = STATE["log"][-4000:]
                STATE["step"] = "idle"
                _termux_notify(f"Lỗi dịch: {title}", f"Mã thoát {proc.returncode}")
                return
                
            STATE["step"] = "done"
            epub_display_path = epub_file if paths["has_custom_output"] else paths["epub_path"].name
            pdf_display_path = pdf_file if paths["has_custom_output"] else paths["pdf_path"].name
            exported = _export_to_android_storage(epub_file)
            _export_to_android_storage(pdf_file)
            if exported:
                target_folder_name = os.path.basename(os.path.dirname(exported))
                STATE["epub"] = f"{epub_display_path} (da copy vao {target_folder_name})"
            else:
                STATE["epub"] = epub_display_path
            STATE["pdf"] = pdf_display_path
            _termux_notify(f"Dịch xong: {title}", f"EPUB và PDF đã sẵn sàng: {paths['epub_path'].name}")
            REGISTERED_OUTPUT_DIRS.add(paths["output_dir"])
                
    except Exception as e:
        with LOCK:
            STATE["running"] = False
            STATE["error"] = f"Loi he thong: {e}"
            STATE["error_detail"] = traceback.format_exc()
            STATE["step"] = "idle"
            CURRENT_PROC = None
            _termux_notify(f"Lỗi hệ thống: {title}", str(e))
    finally:
        _termux_wake_unlock()

def _platform() -> str:
    if _IS_TERMUX:
        return "termux"
    return "windows" if os.name == "nt" else "other"


def _pick_directory_dialog() -> str:
    """Mo hop thoai FolderBrowserDialog tren Windows de nguoi dung chon thu muc."""
    if os.name != "nt":
        return ""
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Chọn thư mục lưu kết quả dịch")
        root.destroy()
        return path or ""
    except Exception:
        return ""


def _library_items(extra_dir=None) -> list:
    """Cac file EPUB/PDF da dong goi trong thu muc lam viec va thu muc dau ra."""
    items = []
    seen_names = set()
    dirs_to_scan = [Path.cwd().resolve()]
    for d in REGISTERED_OUTPUT_DIRS:
        res_d = Path(d).resolve()
        if res_d not in dirs_to_scan:
            dirs_to_scan.append(res_d)
    if extra_dir:
        try:
            p = Path(extra_dir).expanduser().resolve()
            if p.is_dir() and p not in dirs_to_scan:
                dirs_to_scan.append(p)
        except Exception:
            pass

    for directory in dirs_to_scan:
        try:
            entries = list(os.scandir(str(directory)))
        except OSError:
            continue
        for entry in entries:
            suffix = Path(entry.name).suffix.lower()
            if not entry.is_file() or suffix not in (".epub", ".pdf"):
                continue
            if entry.name in (TEST_EPUB_NAME, TEST_PDF_NAME):
                continue
            if entry.name in seen_names:
                continue
            seen_names.add(entry.name)
            try:
                st = entry.stat()
            except OSError:
                continue
            items.append({"name": entry.name, "size": st.st_size, "mtime": int(st.st_mtime)})
    items.sort(key=lambda item: item["mtime"], reverse=True)
    return items


def _request_stop() -> None:
    """Danh dau yeu cau dung va ngat tien trinh pipeline dang chay (neu co)."""
    proc_to_stop = None
    with LOCK:
        if STATE["running"]:
            STATE["error"] = "Stopped"
            STATE["stop_requested"] = True
            proc_to_stop = CURRENT_PROC
    if proc_to_stop:
        try:
            proc_to_stop.terminate()
        except Exception:
            pass
        threading.Thread(target=force_kill_after_grace, args=(proc_to_stop,), daemon=True).start()


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, status, body=b"", content_type=None, headers=None):
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if status != 204:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and status != 204:
            self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def _send_file(self, path, content_type, download_name=None, cache="no-cache"):
        headers = {"Cache-Control": cache}
        if download_name:
            ascii_name = download_name.encode("ascii", "ignore").decode().replace('"', "") or "download"
            quoted = urllib.parse.quote(download_name)
            headers["Content-Disposition"] = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(size))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                shutil.copyfileobj(f, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_form(self):
        length = int(self.headers.get("Content-Length", 0))
        return urllib.parse.parse_qs(self.rfile.read(length).decode())

    def _estimate(self, query):
        input_value = query.get("input", [""])[0].strip()
        title = query.get("title", [""])[0].strip()
        output_dir = query.get("output_dir", [""])[0].strip()
        model = query.get("model", [DEFAULT_MODEL])[0].strip() or DEFAULT_MODEL
        effort = query.get("reasoning_effort", [DEFAULT_REASONING_EFFORT])[0].strip()
        if effort not in REASONING_EFFORTS:
            effort = DEFAULT_REASONING_EFFORT
        no_thinking = query.get("no_thinking", [""])[0].lower() in ("1", "true", "yes", "on")
        allow_peak = query.get("allow_peak", [""])[0].lower() in ("1", "true", "yes", "on")

        if not input_value:
            return {"available": False, "reason": "Chưa có file thô hoặc link."}

        try:
            paths = resolve_pipeline_paths(input_value, title=title, output_dir=output_dir)
        except Exception as exc:
            return {"available": False, "reason": f"Đường dẫn file không hợp lệ: {exc}"}

        if paths["is_url"]:
            raw_path = paths["raw_path"]
            if not raw_path.is_file():
                adapter = find_adapter(input_value)
                if adapter and adapter.is_catalog_url(input_value):
                    return estimate_catalog(input_value, adapter, model=model, reasoning_effort=effort,
                                            no_thinking=no_thinking,
                                            peak=bool(allow_peak and is_peak_hour()))
                return {"available": False,
                        "reason": "Link này chưa được cào nên chưa biết số chương; cào xong mới ước tính được."}
        else:
            raw_path = paths["raw_path"]
            if raw_path.suffix.lower() != ".txt":
                return {"available": False, "reason": "Chỉ đọc file .txt."}
            if not raw_path.is_file():
                return {"available": False, "reason": "Không tìm thấy file thô."}

        translated_path = paths["translated_path"]
        peak = bool(allow_peak and is_peak_hour())
        return estimate_file(raw_path, translated_path if translated_path.is_file() else None,
                             model=model, reasoning_effort=effort,
                             no_thinking=no_thinking, peak=peak)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/status":
            with LOCK:
                body = json.dumps(STATE, ensure_ascii=False)
            self._send(200, body.encode(), "application/json", {"Cache-Control": "no-store"})
        elif path == "/estimate":
            try:
                query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                self._json(self._estimate(query), 200)
            except Exception:
                self._json({"available": False, "reason": "Không thể ước tính file này."}, 400)
        elif path == "/get_key":
            self._json({"key": os.environ.get("DEEPSEEK_API_KEY", "")})
        elif path == "/info":
            self._json({
                "app": "novel-translator",
                "version": __version__,
                "platform": _platform(),
                "frozen": bool(getattr(sys, "frozen", False)),
                "data_dir": os.getcwd(),
                "can_quit": SHUTDOWN_HOOK is not None,
                "can_open_dir": _platform() == "windows",
                "can_pick_dir": _platform() == "windows",
            })
        elif path == "/library":
            output_dir_param = urllib.parse.parse_qs(parsed.query).get("output_dir", [""])[0].strip()
            self._json({"items": _library_items(extra_dir=output_dir_param if output_dir_param else None)})
        elif path == "/download":
            name = urllib.parse.parse_qs(parsed.query).get("name", [""])[0]
            output_dir_param = urllib.parse.parse_qs(parsed.query).get("output_dir", [""])[0].strip()
            if output_dir_param:
                ok, valid_out, _ = validate_output_dir(output_dir_param, create=False)
                if ok and valid_out:
                    REGISTERED_OUTPUT_DIRS.add(valid_out)

            valid_name = (name and name == os.path.basename(name) and not name.startswith(".")
                          and os.sep not in name and (not os.altsep or os.altsep not in name)
                          and Path(name).suffix.lower() in (".epub", ".pdf")
                          and name not in (TEST_EPUB_NAME, TEST_PDF_NAME))

            target_path = None
            if valid_name:
                allowed_roots = [Path.cwd().resolve(), *[Path(d).resolve() for d in REGISTERED_OUTPUT_DIRS]]
                for root_dir in allowed_roots:
                    candidate = root_dir / name
                    if candidate.is_file() and is_safe_path(candidate, allowed_roots):
                        target_path = candidate
                        break

            if target_path:
                content_type = "application/epub+zip" if target_path.suffix.lower() == ".epub" else "application/pdf"
                self._send_file(str(target_path), content_type, download_name=name)
            else:
                self._json({"error": "Khong tim thay file EPUB/PDF"}, 404)
        elif path == "/download_test":
            if TEST_EPUB_PATH and os.path.exists(TEST_EPUB_PATH):
                self._send_file(TEST_EPUB_PATH, "application/epub+zip", download_name=TEST_EPUB_NAME)
            else:
                self._json({"error": "Chua co file EPUB dung thu"}, 404)
        elif path == "/download_test_pdf":
            if TEST_PDF_PATH and os.path.exists(TEST_PDF_PATH):
                self._send_file(TEST_PDF_PATH, "application/pdf", download_name=TEST_PDF_NAME)
            else:
                self._json({"error": "Chua co file PDF dung thu"}, 404)
        elif path.startswith("/assets/"):
            asset = _web_file(urllib.parse.unquote(path[len("/assets/"):]))
            if asset is None:
                self._json({"error": "Khong tim thay"}, 404)
            else:
                cache = "public, max-age=86400" if asset.suffix.lower() == ".woff2" else "no-cache"
                self._send_file(asset, ASSET_TYPES.get(asset.suffix.lower(), "application/octet-stream"), cache=cache)
        elif path in ("/", "/index.html"):
            page = _web_file("index.html")
            if page is None:
                self._send(500, "Thieu thu muc web/ (index.html). Cai lai hoac cap nhat ung dung.".encode("utf-8"),
                           "text/plain; charset=utf-8")
            else:
                self._send_file(page, "text/html; charset=utf-8")
        else:
            self._json({"error": "Khong tim thay"}, 404)

    def do_POST(self):
        if self.path.startswith("/upload_raw"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            filename = sanitize_filename(os.path.basename(qs.get("name", [""])[0]) or "cao_tay.txt")
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            ok, save_path, err = safe_upload_file(UPLOAD_DIR, filename, data)
            if ok and save_path:
                self._json({"success": True, "path": str(save_path)})
            else:
                self._json({"success": False, "message": err or "Khong the luu file"}, 500)
            return

        if self.path == "/pick_directory":
            if _platform() != "windows":
                self._json({"success": False, "message": "Chi ho tro tren Windows"}, 400)
                return
            selected = _pick_directory_dialog()
            self._json({"success": bool(selected), "path": selected or ""})
            return

        if self.path == "/stop":
            _request_stop()
            self._send(204)
            return

        if self.path == "/shutdown":
            if SHUTDOWN_HOOK is None:
                self._json({"error": "Chuc nang nay chi co khi chay bang file .exe"}, 404)
                return
            _request_stop()
            self._send(204)
            threading.Thread(target=SHUTDOWN_HOOK, daemon=True).start()
            return

        if self.path == "/open_data_dir":
            if _platform() != "windows":
                self._json({"error": "Chi ho tro tren Windows"}, 404)
                return
            try:
                os.startfile(os.getcwd())
            except OSError as e:
                self._json({"error": str(e)}, 500)
                return
            self._send(204)
            return

        if self.path == "/save_key":
            params = self._read_form()
            key = params.get("key", [""])[0].strip()
            save_api_key(key)
            self._json({"success": True})
            return

        if self.path == "/test_key":
            params = self._read_form()
            key = params.get("key", [""])[0].strip()
            success, msg = test_deepseek_key(key)
            self._json({"success": success, "message": msg})
            return

        if self.path == "/key_balance":
            params = self._read_form()
            key = params.get("key", [""])[0].strip()
            self._json(get_deepseek_balance(key))
            return

        if self.path == "/test_translate":
            params = self._read_form()
            chinese_text = params.get("text", [""])[0].strip()
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                result = {"success": False, "message": "Chua co API Key. Vui long luu Key truoc."}
            elif not chinese_text:
                result = {"success": False, "message": "Vui long nhap doan van Trung."}
            else:
                result = test_translate_handler(chinese_text, api_key)
            self._json(result)
            return

        params = self._read_form()

        input_val = params.get("input", [""])[0].strip()
        title = params.get("title", [""])[0].strip()
        author = params.get("author", [""])[0].strip()
        model = params.get("model", [DEFAULT_MODEL])[0].strip()
        reasoning_effort = params.get("reasoning_effort", [DEFAULT_REASONING_EFFORT])[0].strip()
        if reasoning_effort not in REASONING_EFFORTS:
            reasoning_effort = DEFAULT_REASONING_EFFORT

        try:
            workers = int(params.get("workers", ["1"])[0].strip())
        except ValueError:
            workers = 1

        try:
            temperature = float(params.get("temperature", ["1.3"])[0].strip())
        except ValueError:
            temperature = 1.3

        allow_peak = "allow_peak" in params
        no_style_detect = "no_style_detect" in params
        no_thinking = "no_thinking" in params
        stream_mode = "stream_mode" in params

        try:
            chapters = int(params.get("chapters", ["0"])[0].strip())
        except ValueError:
            chapters = 0

        output_dir = params.get("output_dir", [""])[0].strip()
        if output_dir:
            ok, resolved_dir, err = validate_output_dir(output_dir, create=True)
            if not ok or resolved_dir is None:
                with LOCK:
                    STATE["error"] = f"Thu muc luu khong hop le: {err}"
                    STATE["step"] = "idle"
                self._send(400)
                return
            REGISTERED_OUTPUT_DIRS.add(resolved_dir)

        with LOCK:
            already_running = STATE["running"]

        if not already_running and input_val:
            threading.Thread(
                target=run_pipeline,
                args=(input_val, title, author, model, workers, temperature, allow_peak, no_style_detect, no_thinking, stream_mode, chapters, reasoning_effort, output_dir),
                daemon=True
            ).start()

        self._send(204)

    def log_message(self, fmt, *args):
        pass  # im lang, poll moi 1s spam terminal khong can thiet


class GuiServer(http.server.ThreadingHTTPServer):
    # Tren Windows SO_REUSEADDR cho phep 2 server cung bind 1 cong (lan nhau, khong bao loi),
    # nen chi bat tren he khac de khoi dong lai nhanh.
    allow_reuse_address = os.name != "nt"


def make_server(host=None, port=8000):
    """Server GUI. Mac dinh chi nghe 127.0.0.1 de nguoi khac trong mang khong doc duoc API key
    qua /get_key; dat NOVEL_GUI_HOST=0.0.0.0 neu that su can truy cap tu may khac."""
    host = host or os.environ.get("NOVEL_GUI_HOST", "127.0.0.1")
    return GuiServer((host, port), Handler)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("GUI web: http://localhost:8000")
    make_server().serve_forever()
