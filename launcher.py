#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diem vao cua ban dong goi .exe (Windows): mo giao dien web trong trinh duyet.

    NovelTranslator.exe               mo giao dien (http://127.0.0.1:8000, doi cong neu ban)
    NovelTranslator.exe --selftest    kiem tra goi cai day du (thu vien, tu dien, giao dien)
    NovelTranslator.exe --worker ...  noi bo: tien trinh con chay pipeline.py cho GUI

Chay tu ma nguon cung duoc: python launcher.py (du lieu nam canh ma nguon).
Du lieu (.env, truyen tho, ban dich, EPUB) nam trong thu muc DuLieu canh file .exe
(hoac %LOCALAPPDATA%\\NovelTranslator neu thu muc exe khong ghi duoc). Dat NOVEL_DATA_DIR
de doi sang thu muc khac.
"""

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_PORT = 8000
FROZEN = bool(getattr(sys, "frozen", False))


def _console_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass


def data_dir() -> Path:
    override = os.environ.get("NOVEL_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    if not FROZEN:
        return Path(__file__).resolve().parent
    candidates = [Path(sys.executable).resolve().parent / "DuLieu"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "NovelTranslator")
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".ghi_thu"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return path
        except OSError:
            continue
    raise SystemExit("Khong tao duoc thu muc du lieu (can quyen ghi canh file .exe hoac trong LOCALAPPDATA).")


def _bind_children_to_process() -> None:
    """Windows: gop tien trinh nay va moi tien trinh con vao 1 Job Object tu huy khi launcher
    chet (dong cua so den, kill tu Task Manager). Khong co no, pipeline dang dich co the mo coi
    tiep tuc chay ngam va ton tien API khi GUI da tat."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return
        kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
        _bind_children_to_process.handle = job  # giu handle song suot tien trinh
    except Exception:
        pass


def _run_worker(argv) -> None:
    """Tien trinh con: chay pipeline.main() voi tham so GUI truyen vao."""
    _console_utf8()
    sys.argv = ["pipeline"] + list(argv)
    import pipeline
    pipeline.main()


def _selftest() -> int:
    """Kiem tra goi cai co du thu vien, tu dien va giao dien. In PASS/FAIL tung muc."""
    _console_utf8()
    failures = []

    def check(name, fn):
        try:
            detail = fn()
            print(f"PASS  {name}" + (f" - {detail}" if detail else ""))
        except Exception as e:  # noqa: BLE001 - bao cao moi loi
            failures.append(name)
            print(f"FAIL  {name} - {type(e).__name__}: {e}")

    def modules():
        import build_epub, cost_estimate, crawler, deepseek_translate, pipeline, prepare_novel, sources, validator, web_gui  # noqa: F401,E401
        return "import du modules"

    def dictionaries():
        import deepseek_translate as dt
        import prepare_novel as pn
        idioms = json.loads(dt._IDIOMS_PATH.read_text(encoding="utf-8"))
        curated = json.loads(dt._CURATED_IDIOMS_PATH.read_text(encoding="utf-8"))
        words = json.loads(pn._HANVIET_WORDS.read_text(encoding="utf-8"))
        assert idioms and curated and words
        sizes = [p.stat().st_size // 1024 for p in (dt._IDIOMS_PATH, dt._CURATED_IDIOMS_PATH, pn._HANVIET_WORDS)]
        return "idioms_verified %d KB, idioms_curated %d KB, hanviet_words %d KB" % tuple(sizes)

    def web_assets():
        import web_gui
        for rel in ("index.html", "app.js", "app.css", "fonts/fonts.css",
                    "fonts/plus-jakarta-sans-vietnamese.woff2", "favicon.svg"):
            assert web_gui._web_file(rel) is not None, rel
        return "index.html, app.js, app.css, font, favicon"

    def opencc_convert():
        import deepseek_translate as dt
        out = dt.normalize_zh("遊戲")
        assert out == "游戏", out
        return "phon the -> gian the OK"

    def holidays_cn():
        import deepseek_translate as dt
        from datetime import datetime
        beijing = datetime(2026, 10, 1, 10, 0, tzinfo=dt.BEIJING_TZ)  # ngay le Quoc khanh, gio thuong la cao diem
        assert dt.is_peak_hour(beijing) is False, "ngay le Trung Quoc van bi tinh cao diem (thieu du lieu holidays)"
        return "ngay le Trung Quoc duoc nhan ra"

    def epub_build():
        import tempfile
        from build_epub import build_epub
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "t.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("=== Chuong 1 ===\n\nXin chao.\n\n" + "=" * 40 + "\n")
            out = os.path.join(tmp, "t.epub")
            build_epub(src, out, "Truyen thu", "Tac gia")
            assert os.path.getsize(out) > 1000
        return "tao EPUB co anh bia OK"

    def data_writable():
        probe = Path(os.getcwd()) / ".selftest_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return f"thu muc du lieu: {os.getcwd()}"

    check("modules", modules)
    check("tu dien", dictionaries)
    check("giao dien web/", web_assets)
    check("opencc", opencc_convert)
    check("ngay le Trung Quoc (holidays)", holidays_cn)
    check("dong goi EPUB", epub_build)
    check("thu muc du lieu ghi duoc", data_writable)
    print("SELFTEST " + ("FAIL: " + ", ".join(failures) if failures else "PASS"))
    return 1 if failures else 0


def _server_is_ours(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/info", timeout=1.5) as resp:
            return json.load(resp).get("app") == "novel-translator"
    except Exception:
        return False


def _open_browser(url: str) -> None:
    def go():
        time.sleep(0.6)
        webbrowser.open(url)
    threading.Thread(target=go, daemon=True).start()


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _run_worker(sys.argv[2:])
        return 0

    _console_utf8()
    os.chdir(data_dir())
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return _selftest()

    port = int(os.environ.get("NOVEL_GUI_PORT", DEFAULT_PORT))
    if _server_is_ours(port):
        url = f"http://127.0.0.1:{port}/"
        print(f"Ung dung dang chay san, mo lai trinh duyet: {url}")
        webbrowser.open(url)
        return 0

    _bind_children_to_process()

    import web_gui
    try:
        server = web_gui.make_server("127.0.0.1", port)
    except OSError:
        server = web_gui.make_server("127.0.0.1", 0)
    port = server.server_address[1]
    web_gui.SHUTDOWN_HOOK = server.shutdown

    url = f"http://127.0.0.1:{port}/"
    print("=" * 60)
    print(" TRINH DICH TRUYEN DEEPSEEK")
    print(f" Giao dien: {url}")
    print(f" Du lieu:   {os.getcwd()}")
    print(" Giu cua so nay mo trong luc dich. Bam 'Thoat ung dung' tren")
    print(" trang web (hoac dong cua so nay) de tat ung dung.")
    print("=" * 60, flush=True)
    _open_browser(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        web_gui._request_stop()
        server.server_close()
    print("Da thoat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
