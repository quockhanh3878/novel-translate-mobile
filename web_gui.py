"""web_gui.py - GUI web toi thieu (chi http.server chuan lib, khong Flask/Tkinter) de
chay pipeline.py (cao -> dich DeepSeek API -> dong goi EPUB) tu trinh duyet dien thoai.

Chay: python web_gui.py roi mo http://localhost:8000
"""
import http.server
import json
import os
import shutil
import subprocess
import threading
import urllib.parse

from crawler import guess_title

STATE = {"running": False, "log": "", "epub": None, "error": None}
LOCK = threading.Lock()

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dich truyen</title>
<style>
body{font-family:sans-serif;max-width:480px;margin:0 auto;padding:16px;background:#111;color:#eee}
input,button{width:100%;box-sizing:border-box;padding:10px;margin:6px 0;font-size:16px;border-radius:6px;border:1px solid #444}
input{background:#222;color:#eee}
button{background:#2e7d32;color:#fff;border:none;font-weight:bold}
button:disabled{background:#555}
pre{white-space:pre-wrap;background:#000;color:#0f0;padding:8px;border-radius:6px;max-height:50vh;overflow-y:auto;font-size:12px}
a{color:#4fc3f7}
</style></head>
<body>
<h3>Dich truyen (DeepSeek API)</h3>
<form id="f">
<input name="input" placeholder="URL chuong 1 hoac duong dan file da cao san" required>
<input name="title" placeholder="Ten truyen (bo trong = tu doan tu URL)">
<button type="submit" id="btn">Bat dau</button>
</form>
<div id="result"></div>
<pre id="log"></pre>
<script>
const f = document.getElementById('f'), btn = document.getElementById('btn');
const logEl = document.getElementById('log'), result = document.getElementById('result');
f.onsubmit = async (e) => {
  e.preventDefault();
  await fetch('/', {method: 'POST', body: new URLSearchParams(new FormData(f))});
  poll();
};
async function poll() {
  const r = await fetch('/status'); const s = await r.json();
  btn.disabled = s.running;
  logEl.textContent = s.log;
  logEl.scrollTop = logEl.scrollHeight;
  result.textContent = s.epub ? ('Xong: ' + s.epub) : (s.error || '');
  if (s.running) setTimeout(poll, 2000);
}
poll();
</script>
</body></html>"""


# Thu muc du an trong Termux la storage rieng cua app, may doc sach khac khong doc
# duoc. termux-setup-storage tao ~/storage/shared tro ve bo nho dung chung Android -
# copy EPUB ra Documents de app doc sach khac tu quet thay.
SHARED_DOCUMENTS = os.path.expanduser("~/storage/shared/Documents")


def run_pipeline(input_val, title):
    title = title or guess_title(input_val)
    args = ["python", "pipeline.py", "--title", title]
    args += (["--start-url", input_val] if input_val.startswith("http") else ["--raw", input_val])
    with LOCK:
        STATE.update(running=True, log="", epub=None, error=None)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        with LOCK:
            STATE["log"] += line
    proc.wait()
    with LOCK:
        STATE["running"] = False
        if proc.returncode != 0:
            STATE["error"] = f"Loi (ma {proc.returncode}), xem log o tren."
            return
        epub_path = f"{title}.epub"
        if os.path.isdir(SHARED_DOCUMENTS):
            shutil.copy(epub_path, SHARED_DOCUMENTS)
            STATE["epub"] = f"{epub_path} (da copy vao Documents)"
        else:
            STATE["epub"] = epub_path


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            with LOCK:
                body = json.dumps(STATE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        params = urllib.parse.parse_qs(self.rfile.read(length).decode())
        input_val = params.get("input", [""])[0].strip()
        title = params.get("title", [""])[0].strip()
        with LOCK:
            already_running = STATE["running"]
        if not already_running and input_val:
            threading.Thread(target=run_pipeline, args=(input_val, title), daemon=True).start()
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # im lang, poll moi 2s spam terminal khong can thiet


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("GUI web: http://localhost:8000")
    http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
