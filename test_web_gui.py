"""Kiem tra offline giao dien web: file tinh, chong ../, thu vien EPUB, tai file, buoc xu ly tu log,
tien trinh con gia (khong goi API that).

Chay: .venv\\Scripts\\python test_web_gui.py
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT)

_work = tempfile.TemporaryDirectory()
os.chdir(_work.name)  # tranh nap .env that cua du an va ghi file rac vao du an
os.environ.pop("DEEPSEEK_API_KEY", None)

import web_gui  # noqa: E402


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def demo():
    # URL identity must remain stable when the display title changes. Existing
    # title-derived files from older GUI versions remain a compatibility fallback.
    with tempfile.TemporaryDirectory() as identity_dir:
        previous_cwd = os.getcwd()
        os.chdir(identity_dir)
        try:
            url = "https://example.com/old-book-name_1.html"
            stable = "Old Book Name_raw.txt"
            legacy = "Old Display Name_raw.txt"
            with open(stable, "w", encoding="utf-8") as handle:
                handle.write("old raw")
            assert web_gui.resolve_raw_file(url, "New Display Name") == stable
            os.remove(stable)
            with open(legacy, "w", encoding="utf-8") as handle:
                handle.write("legacy raw")
            assert web_gui.resolve_raw_file(url, "Old Display Name") == legacy
            os.remove(legacy)
            assert web_gui.resolve_raw_file(url, "New Display Name") == stable
        finally:
            os.chdir(previous_cwd)

    # --- Cac buoc xu ly doc tu log pipeline.py ("=== Buoc N/4: ...") qua tien trinh con gia ---
    def observe(lines, stream_mode):
        """Chay run_pipeline voi tien trinh con in `lines` (cach nhau 0.3s) va ghi lai chuoi
        (buoc, chuong hien tai, tong chuong) ma STATE di qua."""
        script = "import time\nfor line in %r:\n    print(line, flush=True)\n    time.sleep(0.3)\n" % (lines,)
        web_gui._worker_command = lambda: [sys.executable, "-u", "-c", script]
        with web_gui.LOCK:
            web_gui.STATE.update(step="idle", current_chapter=0, total_chapters=0)
        seen = []
        stop = threading.Event()

        def sample():
            while not stop.is_set():
                with web_gui.LOCK:
                    point = (web_gui.STATE["step"], web_gui.STATE["current_chapter"], web_gui.STATE["total_chapters"])
                if not seen or seen[-1] != point:
                    seen.append(point)
                time.sleep(0.02)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Gia", stream_mode=stream_mode)
        stop.set()
        sampler.join()
        with web_gui.LOCK:  # lay mau lan cuoi: run_pipeline vua dat "done" co the nhanh hon chu ky lay mau
            seen.append((web_gui.STATE["step"], web_gui.STATE["current_chapter"], web_gui.STATE["total_chapters"]))
        return seen

    def step_order(seen):
        steps = [step for step, _, _ in seen if step != "idle"]
        return [x for i, x in enumerate(steps) if i == 0 or x != steps[i - 1]]

    original = web_gui._worker_command
    try:
        seen = observe([
            "=== Buoc 1/4: Cao truyen ===",
            "Da luu chuong 7: abc",
            "=== Buoc 2/4: Dich bang DeepSeek API ===",
            "Da phan tich 3 chuong tu x.txt.",
            "[2/3] Chuong 2 -> Chuong 2",
            "=== Buoc 3/4: Kiem tra chat luong (Validation) ===",
            "=== Buoc 4/4: Dong goi EPUB ===",
        ], stream_mode=False)
        assert step_order(seen) == ["crawling", "translating", "validating", "packaging", "done"], seen
        assert ("crawling", 7, 0) in seen, seen
        assert ("translating", 2, 3) in seen, seen

        # che do stream: hai moc dau khong doi buoc (giu "streaming")
        seen = observe([
            "=== Buoc 1/4: Cao truyen ===",
            "=== Buoc 2/4: Dich ngay theo tung chuong vua cao ===",
            "=== Buoc 3/4: Kiem tra chat luong (Validation) ===",
            "=== Buoc 4/4: Dong goi EPUB ===",
        ], stream_mode=True)
        assert step_order(seen) == ["streaming", "validating", "packaging", "done"], seen
    finally:
        web_gui._worker_command = original

    # --- Server: file tinh, chong ../, thu vien, tai file ---
    with open("Dệ Tam.epub", "wb") as f:
        f.write(b"PK-fake-epub")
    with open("test_dung_thu.epub", "wb") as f:
        f.write(b"PK-test")
    with open("bi_mat.txt", "w", encoding="utf-8") as f:
        f.write("khong duoc tai")

    server = web_gui.make_server("127.0.0.1", 0)
    assert server.server_address[0] == "127.0.0.1"
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, headers, body = get(base, "/")
        assert status == 200 and b"/assets/app.js" in body and b"estimate-crawled" in body \
            and b"estimate-balance" in body and "text/html" in headers["Content-Type"]
        for asset in ("/assets/app.js", "/assets/app.css", "/assets/fonts/fonts.css",
                      "/assets/fonts/plus-jakarta-sans-vietnamese.woff2", "/assets/favicon.svg"):
            status, headers, body = get(base, asset)
            assert status == 200 and len(body) > 50, asset
        assert get(base, "/assets/fonts/plus-jakarta-sans-vietnamese.woff2")[1]["Content-Type"] == "font/woff2"

        # chong ../ va file ngoai web/ hoac sai duoi
        for bad in ("/assets/../web_gui.py", "/assets/%2e%2e/web_gui.py", "/assets/..%5Cweb_gui.py",
                    "/assets/fonts/OFL-LICENSE.md", "/assets/nope.js", "/khong-co", "/favicon.ico"):
            assert get(base, bad)[0] == 404, bad

        status, _, body = get(base, "/info")
        info = json.loads(body)
        assert status == 200 and info["app"] == "novel-translator" and info["version"]
        assert info["can_quit"] is False and os.path.samefile(info["data_dir"], _work.name)

        status, _, body = get(base, "/library")
        names = [item["name"] for item in json.loads(body)["items"]]
        assert names == ["Dệ Tam.epub"], names  # khong liet ke file dich thu

        quoted = urllib.parse.quote("Dệ Tam.epub")
        status, headers, body = get(base, "/download?name=" + quoted)
        assert status == 200 and body == b"PK-fake-epub"
        assert headers["Content-Type"] == "application/epub+zip"
        assert "filename*=UTF-8''" + quoted in headers["Content-Disposition"]
        for bad in ("../web_gui.py", "..%5Cweb_gui.py", "bi_mat.txt", "test_dung_thu.epub", ".env", ""):
            assert get(base, "/download?name=" + bad)[0] == 404, bad

        # Test safe upload qua /upload_raw
        upload_data = "Noi dung upload an toan".encode("utf-8")
        req_up = urllib.request.Request(base + "/upload_raw?name=truyen_test.txt", method="POST", data=upload_data)
        with urllib.request.urlopen(req_up, timeout=5) as resp:
            assert resp.status == 200
            up_res = json.loads(resp.read().decode())
            assert up_res["success"] is True and os.path.isfile(up_res["path"])
            with open(up_res["path"], "rb") as uf:
                assert uf.read() == upload_data

        # Test library va download voi output_dir tuy chon
        custom_out_dir = os.path.join(_work.name, "CustomOutput")
        os.makedirs(custom_out_dir, exist_ok=True)
        custom_epub = os.path.join(custom_out_dir, "CustomTruyen.epub")
        with open(custom_epub, "wb") as f:
            f.write(b"PK-custom-epub")

        # Goi /library co tham so output_dir
        status, _, body = get(base, "/library?output_dir=" + urllib.parse.quote(custom_out_dir))
        names = [item["name"] for item in json.loads(body)["items"]]
        assert "CustomTruyen.epub" in names, names

        # Tai file tu custom output_dir
        status, headers, body = get(base, "/download?name=" + urllib.parse.quote("CustomTruyen.epub") + "&output_dir=" + urllib.parse.quote(custom_out_dir))
        assert status == 200 and body == b"PK-custom-epub"

        # /shutdown va /open_data_dir chi co khi launcher gan SHUTDOWN_HOOK / tren Windows
        req = urllib.request.Request(base + "/shutdown", method="POST", data=b"")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("/shutdown phai bi tu choi khi khong co hook")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()
        server.server_close()

    # --- run_pipeline voi tien trinh con gia: thanh cong -> step done + epub; loi -> error_detail ---
    original = web_gui._worker_command
    try:
        fake_ok = "import sys; print('=== Buoc 4/4: Dong goi EPUB ==='); print('Hoan tat!')"
        web_gui._worker_command = lambda: [sys.executable, "-u", "-c", fake_ok]
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Gia")
        assert web_gui.STATE["running"] is False and web_gui.STATE["step"] == "done", web_gui.STATE
        assert web_gui.STATE["epub"] == "Truyen Gia.epub" and web_gui.STATE["error"] is None

        # Test run_pipeline voi output_dir tuy chon
        job_out_dir = os.path.join(_work.name, "JobOutput")
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Job", output_dir=job_out_dir)
        assert web_gui.STATE["running"] is False and web_gui.STATE["step"] == "done"
        assert web_gui.STATE["output_dir"] == str(Path(job_out_dir).resolve())
        assert web_gui.STATE["epub"] == str(Path(job_out_dir).resolve() / "Truyen Job.epub")

        fake_bad = "import sys; print('boom'); sys.exit(3)"
        web_gui._worker_command = lambda: [sys.executable, "-u", "-c", fake_bad]
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Gia")
        assert web_gui.STATE["step"] == "idle" and "3" in web_gui.STATE["error"], web_gui.STATE
        assert "boom" in web_gui.STATE["error_detail"]
    finally:
        web_gui._worker_command = original

    print("OK: giao dien tinh, chong ../, thu vien/tai EPUB, buoc xu ly tu log, tien trinh con thanh cong/loi dung nhu ky vong.")


if __name__ == "__main__":
    try:
        demo()
    finally:
        os.chdir(PROJECT)
        _work.cleanup()
