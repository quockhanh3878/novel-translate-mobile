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
from unittest.mock import Mock

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


def check_client_disconnects():
    def handler():
        instance = web_gui.Handler.__new__(web_gui.Handler)
        instance.send_response = Mock()
        instance.send_header = Mock()
        instance.end_headers = Mock()
        instance.wfile = Mock()
        instance.close_connection = False
        return instance

    with tempfile.TemporaryDirectory() as directory:
        asset = Path(directory) / "sample.txt"
        asset.write_bytes(b"sample")
        for send_file in (False, True):
            for stage in ("headers", "body"):
                for error in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    instance = handler()
                    writer = instance.end_headers if stage == "headers" else instance.wfile.write
                    writer.side_effect = error("client disconnected")
                    if send_file:
                        instance._send_file(str(asset), "text/plain")
                    else:
                        instance._json({"available": True})
                    assert instance.close_connection is True, (send_file, stage, error)

            instance = handler()
            instance.wfile.write.side_effect = PermissionError("unexpected I/O failure")
            try:
                if send_file:
                    instance._send_file(str(asset), "text/plain")
                else:
                    instance._json({"available": True})
            except PermissionError:
                pass
            else:
                raise AssertionError("Unexpected I/O errors must propagate")

    instance = handler()
    instance._json({"available": True})
    instance.send_response.assert_called_once_with(200)
    instance.wfile.write.assert_called_once_with(b'{"available": true}')
    assert instance.close_connection is False


def demo():
    check_client_disconnects()
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
            # Truyen moi: ten file kem ten trang de khong trung truyen cung slug o trang khac.
            assert web_gui.resolve_raw_file(url, "New Display Name") == "Old Book Name (example.com)_raw.txt"
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
            "Found 10 chapters in https://www.tianyabooks.com/net/csx_03/.",
            "Da luu chuong 7: abc",
            "=== Buoc 2/4: Dich bang DeepSeek API ===",
            "Da phan tich 3 chuong tu x.txt.",
            "[2/3] Chuong 2 -> Chuong 2",
            "=== Buoc 3/4: Kiem tra chat luong (Validation) ===",
            "=== Buoc 4/4: Dong goi EPUB ===",
        ], stream_mode=False)
        assert step_order(seen) == ["crawling", "translating", "validating", "packaging", "done"], seen
        assert ("crawling", 7, 10) in seen, seen
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
    # Ban dich de /export dong goi theo yeu cau (khong co file EPUB/PDF nao duoc tao san)
    with open("truyen_xuat.txt", "w", encoding="utf-8") as f:
        f.write("=== TRUYEN ===\n\n=== 第1章 ===\n\nDong mot.\n\n" + "=" * 40 + "\n\n")
    with open("truyen_xuat.txt.viet.txt", "w", encoding="utf-8") as f:
        f.write("=== Truyện ===\n\n=== Chương 1 ===\n\nDòng một.\n\n" + "=" * 40 + "\n\n")

    server = web_gui.make_server("127.0.0.1", 0)
    assert server.server_address[0] == "127.0.0.1"
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, headers, body = get(base, "/")
        assert status == 200 and b"/assets/app.js" in body and b"estimate-crawled" in body \
            and b"estimate-balance" in body and "text/html" in headers["Content-Type"]
        for domain in (
            b"uukanshu.cc",
            b"69shuba.com",
            b"bgq99.cc",
            b"shubaow.net",
            b"biquge.tw",
            b"tianyabooks.com",
            b"wa01.com",
            b"update_termux.sh",
            b"web_gui.log",
        ):
            assert domain in body, domain
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
        assert set(info.get("supported_sources", [])) == {
            "uukanshu.cc",
            "69shuba.com",
            "bgq99.cc",
            "shubaow.net",
            "biquge.tw",
            "tianyabooks.com",
            "wa01.com",
        }, info

        # /library va /download da bo: khong liet ke san, file chi dong goi khi nguoi dung bam tai
        assert get(base, "/library")[0] == 404
        assert get(base, "/download?name=" + urllib.parse.quote("Dệ Tam.epub"))[0] == 404

        # /export: dong goi EPUB va PDF tu ban dich co san, ten file lay theo tieu de
        export_q = ("input=truyen_xuat.txt&title=" + urllib.parse.quote("Truyện Xuất")
                    + "&author=" + urllib.parse.quote("Tác Giả"))
        status, headers, body = get(base, "/export?format=epub&" + export_q)
        assert status == 200 and body[:2] == b"PK", (status, body[:80])
        assert headers["Content-Type"] == "application/epub+zip"
        assert "filename*=UTF-8''" + urllib.parse.quote("Truyện Xuất.epub") in headers["Content-Disposition"], \
            headers["Content-Disposition"]
        epub_path = os.path.join(_work.name, "Truyện Xuất.epub")
        assert os.path.isfile(epub_path)
        mtime = os.path.getmtime(epub_path)
        status, _, body = get(base, "/export?format=epub&" + export_q)  # ban dich khong doi: khong dong goi lai
        assert status == 200 and body[:2] == b"PK" and os.path.getmtime(epub_path) == mtime

        status, headers, body = get(base, "/export?format=pdf&" + export_q)
        assert status == 200 and body[:4] == b"%PDF" and headers["Content-Type"] == "application/pdf"

        for bad_query in ("format=docx&" + export_q, "format=epub&input=chua_dich.txt", "format=epub"):
            status, _, body = get(base, "/export?" + bad_query)
            assert status == 400 and json.loads(body)["ok"] is False, (bad_query, status, body)

        # Test safe upload qua /upload_raw
        upload_data = "Noi dung upload an toan".encode("utf-8")
        req_up = urllib.request.Request(base + "/upload_raw?name=truyen_test.txt", method="POST", data=upload_data)
        with urllib.request.urlopen(req_up, timeout=5) as resp:
            assert resp.status == 200
            up_res = json.loads(resp.read().decode())
            assert up_res["success"] is True and os.path.isfile(up_res["path"])
            with open(up_res["path"], "rb") as uf:
                assert uf.read() == upload_data

        saved_html = {
            "files": [{
                "name": "sample_1.html",
                "html": "<div class='title'>Chapter 1</div><div class='content'>"
                        "<p>A saved chapter with enough text to import.</p></div>",
            }]
        }
        req_html = urllib.request.Request(
            base + "/import_html", method="POST",
            data=json.dumps(saved_html).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_html, timeout=5) as resp:
            html_result = json.loads(resp.read().decode("utf-8"))
        assert html_result["success"] and html_result["chapters"] == 1
        with open(html_result["path"], "r", encoding="utf-8") as imported:
            imported_text = imported.read()
        assert "=== Chapter 1 ===" in imported_text
        assert "A saved chapter with enough text to import." in imported_text

        blocked_html = {"files": [{"name": "blocked.html", "html": "challenge_required"}]}
        req_blocked = urllib.request.Request(
            base + "/import_html", method="POST", data=json.dumps(blocked_html).encode("utf-8"),
        )
        try:
            urllib.request.urlopen(req_blocked, timeout=5)
            raise AssertionError("A saved challenge page must not be imported as chapter text.")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400 and "xac minh" in exc.read().decode("utf-8")

        # /export voi output_dir tuy chon: raw + ban dich nam trong thu muc do, file dong goi luu o do
        custom_out_dir = os.path.join(_work.name, "CustomOutput")
        os.makedirs(custom_out_dir, exist_ok=True)
        with open(os.path.join(custom_out_dir, "truyen_xuat.txt"), "w", encoding="utf-8") as f:
            f.write("=== TRUYEN ===\n\n=== 第1章 ===\n\nDong mot.\n\n" + "=" * 40 + "\n\n")
        with open(os.path.join(custom_out_dir, "truyen_xuat.txt.viet.txt"), "w", encoding="utf-8") as f:
            f.write("=== Truyện ===\n\n=== Chương 1 ===\n\nDòng một.\n\n" + "=" * 40 + "\n\n")
        custom_raw = os.path.join(custom_out_dir, "truyen_xuat.txt")
        status, headers, body = get(base, "/export?format=pdf&input=" + urllib.parse.quote(custom_raw)
                                    + "&title=CustomTruyen&output_dir=" + urllib.parse.quote(custom_out_dir))
        assert status == 200 and body[:4] == b"%PDF", (status, body[:80])
        assert os.path.isfile(os.path.join(custom_out_dir, "CustomTruyen.pdf"))

        # /replace_chapters: chuong cung so trong file nap thay chuong cu, ban dich chuong do bi bo
        with open("truyen_sua.txt", "w", encoding="utf-8") as f:
            f.write("=== TRUYEN ===\n\n=== 第1章 ===\n\nBan cu.\n\n" + "=" * 40 + "\n\n")
        with open("truyen_sua.txt.viet.txt", "w", encoding="utf-8") as f:
            f.write("=== Truyện ===\n\n=== Chương 1 ===\n\nBản cũ.\n\n" + "=" * 40 + "\n\n")
        fix_req = urllib.request.Request(
            base + "/replace_chapters?name=sua.txt&input=" + urllib.parse.quote("truyen_sua.txt"),
            method="POST", data="=== 第1章 ===\n\nBan sua dung.\n\n".encode("utf-8"))
        with urllib.request.urlopen(fix_req, timeout=5) as resp:
            fix_res = json.loads(resp.read().decode("utf-8"))
        assert fix_res["ok"] and fix_res["replaced"] == 1 and fix_res["appended"] == 0, fix_res
        with open("truyen_sua.txt", encoding="utf-8") as f:
            assert "Ban sua dung." in f.read()
        from crawler import parse_chapters
        assert not [c for c in parse_chapters("truyen_sua.txt.viet.txt") if c["paragraphs"]]  # chuong 1 da bo ban dich
        try:
            urllib.request.urlopen(urllib.request.Request(
                base + "/replace_chapters?name=sua.txt&input=" + urllib.parse.quote("chua_co.txt"),
                method="POST", data=b"=== 1 ===\n\nx\n\n"), timeout=5)
            raise AssertionError("Nap chuong khi chua co file tho phai bi tu choi")
        except urllib.error.HTTPError as e:
            assert e.code == 400 and "Chua co file tho" in json.loads(e.read().decode("utf-8"))["message"]

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
        assert web_gui.STATE["epub"] == "Truyen Gia.epub" and web_gui.STATE["pdf"] == "Truyen Gia.pdf" and web_gui.STATE["error"] is None

        # Test run_pipeline voi output_dir tuy chon
        job_out_dir = os.path.join(_work.name, "JobOutput")
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Job", output_dir=job_out_dir)
        assert web_gui.STATE["running"] is False and web_gui.STATE["step"] == "done"
        assert web_gui.STATE["output_dir"] == str(Path(job_out_dir).resolve())
        assert web_gui.STATE["epub"] == str(Path(job_out_dir).resolve() / "Truyen Job.epub")
        assert web_gui.STATE["pdf"] == str(Path(job_out_dir).resolve() / "Truyen Job.pdf")

        fake_bad = "import sys; print('boom'); sys.exit(3)"
        web_gui._worker_command = lambda: [sys.executable, "-u", "-c", fake_bad]
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Gia")
        assert web_gui.STATE["step"] == "idle" and "3" in web_gui.STATE["error"], web_gui.STATE
        assert "boom" in web_gui.STATE["error_detail"]

        # "Cao tu chuong" chuyen xuong pipeline.py thanh --from-chapter
        orig_meta = web_gui.run_metadata
        web_gui.run_metadata = lambda raw, tr, url, title, author, model: {"display_title": title, "author": ""}
        web_gui._worker_command = lambda: [sys.executable, "-u", "-c", "import sys; print(sys.argv)"]
        try:
            web_gui.run_pipeline("https://example.com/book_1.html", "Truyen Url", crawl_only=True, from_chapter=850)
            assert "'--from-chapter', '850'" in web_gui.STATE["log"], web_gui.STATE["log"]
            web_gui.run_pipeline("https://example.com/book_1.html", "Truyen Url", crawl_only=True)
            assert "--from-chapter" not in web_gui.STATE["log"], web_gui.STATE["log"]
        finally:
            web_gui.run_metadata = orig_meta
    finally:
        web_gui._worker_command = original

    print("OK: giao dien tinh, chong ../, thu vien/tai EPUB, buoc xu ly tu log, tien trinh con thanh cong/loi dung nhu ky vong.")


if __name__ == "__main__":
    try:
        demo()
    finally:
        os.chdir(PROJECT)
        _work.cleanup()
