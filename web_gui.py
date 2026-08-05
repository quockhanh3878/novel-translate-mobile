"""web_gui.py - GUI web toi thieu (chi http.server chuan lib, khong Flask/Tkinter) de
chay pipeline.py (cao -> dich DeepSeek API -> dong goi EPUB) tu trinh duyet dien thoai.

Chay: python web_gui.py roi mo http://localhost:8000
"""
import http.server
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.parse

from crawler import guess_title

# Trạng thái toàn cục để web cap nhat realtime
STATE = {
    "running": False,
    "log": "",
    "epub": None,
    "error": None,
    "step": "idle",          # "idle", "crawling", "translating", "packaging", "done"
    "current_chapter": 0,
    "total_chapters": 0
}
LOCK = threading.Lock()
CURRENT_PROC = None

PAGE = """<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Trình dịch Truyện DeepSeek</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-gradient: radial-gradient(circle at top, #1e2235 0%, #0d0f17 100%);
            --glass-bg: rgba(22, 28, 45, 0.6);
            --glass-border: rgba(255, 255, 255, 0.08);
            --text-main: #e2e8f0;
            --text-muted: #94a3b8;
            --accent-cyan: #00f2fe;
            --accent-blue: #4facfe;
            --accent-green: #10b981;
            --accent-red: #f43f5e;
            --btn-start-grad: linear-gradient(135deg, #00b4db 0%, #0083b0 100%);
            --btn-stop-grad: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%);
        }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg-gradient);
            color: var(--text-main);
            margin: 0;
            min-height: 100vh;
            padding: 20px;
            box-sizing: border-box;
        }
        .container {
            max-width: 600px;
            margin: 40px auto;
            padding: 32px;
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        }
        h2 {
            font-size: 28px;
            font-weight: 700;
            text-align: center;
            margin-top: 0;
            margin-bottom: 24px;
            background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-blue) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }
        .subtitle {
            text-align: center;
            font-size: 14px;
            color: var(--text-muted);
            margin-top: -20px;
            margin-bottom: 30px;
        }
        label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            color: #cbd5e1;
            margin-top: 12px;
        }
        input, select {
            width: 100%;
            box-sizing: border-box;
            padding: 12px 16px;
            margin: 6px 0 16px 0;
            background: rgba(10, 12, 22, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #fff;
            font-size: 15px;
            border-radius: 10px;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        input:focus, select:focus {
            outline: none;
            border-color: var(--accent-cyan);
            box-shadow: 0 0 12px rgba(0, 242, 254, 0.2);
            background: rgba(10, 12, 22, 0.8);
        }
        details {
            margin-bottom: 20px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.01);
            overflow: hidden;
        }
        summary {
            padding: 12px 16px;
            font-weight: 600;
            cursor: pointer;
            color: var(--text-muted);
            user-select: none;
            transition: color 0.2s ease;
            outline: none;
        }
        summary:hover {
            color: var(--accent-cyan);
        }
        .advanced-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            padding: 16px;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            background: rgba(0, 0, 0, 0.15);
        }
        .col-span-2 {
            grid-column: span 2;
        }
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 8px 0;
            color: #cbd5e1;
            font-size: 14px;
        }
        .checkbox-group input {
            width: auto;
            margin: 0;
            cursor: pointer;
            height: 18px;
            width: 18px;
            accent-color: var(--accent-cyan);
        }
        .btn-group {
            display: flex;
            gap: 12px;
            margin-top: 20px;
        }
        button {
            flex: 1;
            padding: 14px;
            font-size: 16px;
            font-weight: 700;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        #btn-start {
            background: var(--btn-start-grad);
            color: #fff;
            box-shadow: 0 4px 15px rgba(0, 180, 219, 0.3);
        }
        #btn-start:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 180, 219, 0.5);
        }
        #btn-start:active:not(:disabled) {
            transform: translateY(0);
        }
        #btn-start:disabled {
            background: #334155;
            color: #64748b;
            box-shadow: none;
            cursor: not-allowed;
        }
        #btn-stop {
            background: var(--btn-stop-grad);
            color: #fff;
            box-shadow: 0 4px 15px rgba(244, 63, 94, 0.3);
            display: none;
        }
        #btn-stop:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(244, 63, 94, 0.5);
        }
        #btn-stop:active {
            transform: translateY(0);
        }
        .steps {
            display: flex;
            justify-content: space-between;
            margin: 24px 0;
            position: relative;
        }
        .steps::before {
            content: '';
            position: absolute;
            top: 16px;
            left: 8%;
            right: 8%;
            height: 2px;
            background: #334155;
            z-index: 1;
        }
        .step {
            display: flex;
            flex-direction: column;
            align-items: center;
            z-index: 2;
            font-size: 11px;
            color: #64748b;
            font-weight: 600;
            width: 25%;
            text-align: center;
        }
        .step-dot {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: #1e293b;
            border: 2px solid #334155;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 8px;
            font-weight: 700;
            font-size: 13px;
            transition: all 0.3s ease;
            color: #64748b;
        }
        .step.active {
            color: var(--accent-cyan);
        }
        .step.active .step-dot {
            background: #0d1e2d;
            border-color: var(--accent-cyan);
            box-shadow: 0 0 15px rgba(0, 242, 254, 0.6);
            color: var(--accent-cyan);
            animation: pulse 2s infinite;
        }
        .step.completed {
            color: var(--accent-green);
        }
        .step.completed .step-dot {
            background: var(--accent-green);
            border-color: var(--accent-green);
            color: #fff;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(0, 242, 254, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(0, 242, 254, 0); }
            100% { box-shadow: 0 0 0 0 rgba(0, 242, 254, 0); }
        }
        .progress-container {
            margin: 24px 0;
            display: none;
        }
        .progress-info {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            margin-bottom: 8px;
            color: var(--text-muted);
            font-weight: 500;
        }
        .progress-bar-bg {
            width: 100%;
            height: 8px;
            background: #1e293b;
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, var(--accent-cyan), var(--accent-blue));
            box-shadow: 0 0 8px rgba(0, 242, 254, 0.4);
            border-radius: 4px;
            transition: width 0.4s ease;
        }
        .result-box {
            margin-top: 24px;
            padding: 16px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            display: none;
            text-align: center;
        }
        .result-box.success {
            display: block;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #34d399;
        }
        .result-box.error {
            display: block;
            background: rgba(244, 63, 94, 0.1);
            border: 1px solid rgba(244, 63, 94, 0.2);
            color: #f87171;
        }
        .console-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 28px;
            margin-bottom: 8px;
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
        }
        .console-controls {
            display: flex;
            gap: 8px;
        }
        .console-btn {
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: var(--text-muted);
            padding: 4px 10px;
            font-size: 11px;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
            font-weight: 600;
        }
        .console-btn:hover {
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border-color: rgba(255, 255, 255, 0.3);
        }
        .console-btn.active {
            background: rgba(0, 242, 254, 0.1);
            color: var(--accent-cyan);
            border-color: rgba(0, 242, 254, 0.3);
        }
        pre {
            margin: 0;
            white-space: pre-wrap;
            background: #060810;
            color: #38bdf8;
            padding: 16px;
            border-radius: 12px;
            max-height: 250px;
            overflow-y: auto;
            font-size: 12px;
            font-family: 'Fira Code', 'Courier New', monospace;
            border: 1px solid rgba(255, 255, 255, 0.05);
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>DỊCH TRUYỆN NOVEL</h2>
        <div class="subtitle">Hệ thống dịch thuật tự động sử dụng DeepSeek API</div>
        
        <form id="f">
            <label>Nguồn truyện:</label>
            <input name="input" placeholder="URL chương 1 (ví dụ: ..._1.html) hoặc đường dẫn file .txt thô" required>
            
            <label>Tên truyện (để trống sẽ tự đoán từ URL):</label>
            <input name="title" placeholder="Ví dụ: Đệ Tam Trùng Nhân Cách">
            
            <details>
                <summary>⚙️ Cấu hình nâng cao</summary>
                <div class="advanced-grid">
                    <div>
                        <label>Tác giả:</label>
                        <input name="author" placeholder="Ví dụ: Thường Thư Hân">
                    </div>
                    <div>
                        <label>Model dịch:</label>
                        <select name="model">
                            <option value="deepseek-v4-flash">deepseek-v4-flash (Khuyên dùng)</option>
                            <option value="deepseek-chat">deepseek-chat</option>
                        </select>
                    </div>
                    <div>
                        <label>Số luồng dịch song song (Workers):</label>
                        <input type="number" name="workers" min="1" max="10" value="1">
                    </div>
                    <div>
                        <label>Độ sáng tạo (Temperature):</label>
                        <input type="number" name="temperature" step="0.1" min="0.0" max="2.0" value="1.3">
                    </div>
                    
                    <div class="col-span-2">
                        <div class="checkbox-group">
                            <input type="checkbox" name="allow_peak" id="allow_peak">
                            <label for="allow_peak" style="display:inline;margin:0;font-weight:normal;">Cho phép dịch trong giờ cao điểm (Giá gấp đôi)</label>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" name="no_style_detect" id="no_style_detect">
                            <label for="no_style_detect" style="display:inline;margin:0;font-weight:normal;">Không tự động phân tích văn phong chương đầu</label>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" name="no_thinking" id="no_thinking">
                            <label for="no_thinking" style="display:inline;margin:0;font-weight:normal;">Tắt Thinking Mode (Không khuyến khích - có thể gây lỗi dịch)</label>
                        </div>
                    </div>
                </div>
            </details>
            
            <div class="btn-group">
                <button type="submit" id="btn-start">Bắt đầu dịch</button>
                <button type="button" id="btn-stop">Dừng lại</button>
            </div>
        </form>
        
        <div class="steps">
            <div class="step" id="step-crawl">
                <div class="step-dot">1</div>
                Cào truyện
            </div>
            <div class="step" id="step-translate">
                <div class="step-dot">2</div>
                Dịch thuật
            </div>
            <div class="step" id="step-package">
                <div class="step-dot">3</div>
                Đóng gói EPUB
            </div>
            <div class="step" id="step-done">
                <div class="step-dot">✓</div>
                Hoàn tất
            </div>
        </div>
        
        <div class="progress-container" id="progress-area">
            <div class="progress-info">
                <span id="progress-text">Đang dịch...</span>
                <span id="progress-percent">0%</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar" id="progress-bar"></div>
            </div>
        </div>
        
        <div class="result-box" id="result"></div>
        
        <div class="console-header">
            <span>CONSOLE LOGS</span>
            <div class="console-controls">
                <button class="console-btn active" id="btn-scroll">Auto Scroll: ON</button>
                <button class="console-btn" id="btn-copy">Copy Logs</button>
            </div>
        </div>
        <pre id="log"></pre>
    </div>
    
    <script>
        const f = document.getElementById('f');
        const btnStart = document.getElementById('btn-start');
        const btnStop = document.getElementById('btn-stop');
        const logEl = document.getElementById('log');
        const resultEl = document.getElementById('result');
        const progressArea = document.getElementById('progress-area');
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        const progressPercent = document.getElementById('progress-percent');
        const btnScroll = document.getElementById('btn-scroll');
        const btnCopy = document.getElementById('btn-copy');
        
        let autoScroll = true;
        let pollTimeout = null;
        
        btnScroll.onclick = () => {
            autoScroll = !autoScroll;
            btnScroll.textContent = 'Auto Scroll: ' + (autoScroll ? 'ON' : 'OFF');
            btnScroll.classList.toggle('active', autoScroll);
        };
        
        btnCopy.onclick = () => {
            navigator.clipboard.writeText(logEl.textContent);
            const originalText = btnCopy.textContent;
            btnCopy.textContent = 'Copied!';
            setTimeout(() => btnCopy.textContent = originalText, 1500);
        };
        
        f.onsubmit = async (e) => {
            e.preventDefault();
            resultEl.style.display = 'none';
            resultEl.className = 'result-box';
            
            const formData = new FormData(f);
            const params = new URLSearchParams();
            
            for (const [key, value] of formData.entries()) {
                params.append(key, value);
            }
            
            await fetch('/', { method: 'POST', body: params });
            if (pollTimeout) clearTimeout(pollTimeout);
            poll();
        };
        
        btnStop.onclick = async () => {
            btnStop.disabled = true;
            await fetch('/stop', { method: 'POST' });
        };
        
        function updateSteps(currentStep) {
            const steps = ['crawling', 'translating', 'packaging', 'done'];
            const stepIds = {
                'crawling': 'step-crawl',
                'translating': 'step-translate',
                'packaging': 'step-package',
                'done': 'step-done'
            };
            
            steps.forEach(s => {
                const el = document.getElementById(stepIds[s]);
                if (el) el.className = 'step';
            });
            
            if (currentStep === 'idle') return;
            
            const activeIdx = steps.indexOf(currentStep);
            
            steps.forEach((s, idx) => {
                const el = document.getElementById(stepIds[s]);
                if (!el) return;
                
                if (idx < activeIdx) {
                    el.className = 'step completed';
                } else if (idx === activeIdx) {
                    el.className = 'step active';
                }
            });
            
            if (currentStep === 'done') {
                document.getElementById('step-done').className = 'step completed';
            }
        }
        
        async function poll() {
            try {
                const r = await fetch('/status');
                const s = await r.json();
                
                btnStart.disabled = s.running;
                if (s.running) {
                    btnStop.style.display = 'block';
                    btnStop.disabled = false;
                } else {
                    btnStop.style.display = 'none';
                }
                
                logEl.textContent = s.log;
                if (autoScroll) {
                    logEl.scrollTop = logEl.scrollHeight;
                }
                
                updateSteps(s.step);
                
                if (s.running && (s.step === 'crawling' || s.step === 'translating')) {
                    progressArea.style.display = 'block';
                    if (s.step === 'crawling') {
                        progressText.textContent = `Đang cào chương: ${s.current_chapter}`;
                        progressBar.style.width = '100%';
                        progressPercent.textContent = 'Đang tải...';
                    } else if (s.step === 'translating') {
                        if (s.total_chapters > 0) {
                            const percent = Math.min(100, Math.round((s.current_chapter / s.total_chapters) * 100));
                            progressText.textContent = `Đang dịch: ${s.current_chapter}/${s.total_chapters} chương`;
                            progressBar.style.width = `${percent}%`;
                            progressPercent.textContent = `${percent}%`;
                        } else {
                            progressText.textContent = `Đang dịch: ${s.current_chapter} chương`;
                            progressBar.style.width = '100%';
                            progressPercent.textContent = 'Đang dịch...';
                        }
                    }
                } else if (s.step === 'packaging') {
                    progressArea.style.display = 'block';
                    progressText.textContent = 'Đang đóng gói file EPUB...';
                    progressBar.style.width = '100%';
                    progressPercent.textContent = '100%';
                } else {
                    progressArea.style.display = 'none';
                }
                
                if (s.epub) {
                    resultEl.textContent = 'Thành công! File EPUB lưu tại: ' + s.epub;
                    resultEl.className = 'result-box success';
                } else if (s.error) {
                    resultEl.textContent = 'Lỗi: ' + s.error;
                    resultEl.className = 'result-box error';
                } else {
                    resultEl.style.display = 'none';
                }
                
                if (s.running) {
                    pollTimeout = setTimeout(poll, 1000);
                }
            } catch (err) {
                console.error("Polling error:", err);
                pollTimeout = setTimeout(poll, 2000);
            }
        }
        poll();
    </script>
</body>
</html>
"""

# Thu muc Documents chung tren Android Termux de app doc sach de dang quet thay
SHARED_DOCUMENTS = os.path.expanduser("~/storage/shared/Documents")

def run_pipeline(input_val, title, author="", model="deepseek-v4-flash", workers=1, temperature=1.3, allow_peak=False, no_style_detect=False, no_thinking=False):
    title = title or guess_title(input_val)
    args = ["python", "pipeline.py", "--title", title]
    if author:
        args += ["--author", author]
    args += ["--model", model]
    args += ["--workers", str(workers)]
    args += ["--temperature", str(temperature)]
    if allow_peak:
        args += ["--allow-peak"]
    if no_style_detect:
        args += ["--no-style-detect"]
    if no_thinking:
        args += ["--no-thinking"]
    
    args += (["--start-url", input_val] if input_val.startswith("http") else ["--raw", input_val])
    
    global CURRENT_PROC
    with LOCK:
        STATE.update(
            running=True,
            log="",
            epub=None,
            error=None,
            step="crawling",
            current_chapter=0,
            total_chapters=0
        )
        
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8", errors="replace")
        with LOCK:
            CURRENT_PROC = proc
            
        for line in proc.stdout:
            with LOCK:
                STATE["log"] += line
                
                # Parse steps
                if "=== Buoc 1/3: Cao truyen ===" in line:
                    STATE["step"] = "crawling"
                elif "=== Buoc 2/3: Dich bang DeepSeek API ===" in line:
                    STATE["step"] = "translating"
                elif "=== Buoc 3/3: Dong goi EPUB ===" in line:
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
            
            # Neu bi terminate hoac gui loi dung
            if proc.returncode == -15 or proc.returncode == 15 or proc.returncode == 1 or STATE["error"] == "Stopped":
                if STATE["error"] == "Stopped":
                    STATE["error"] = "Da dung theo yeu cau."
                else:
                    STATE["error"] = "Da dung hoac gap loi he thong."
                STATE["step"] = "idle"
                return
                
            if proc.returncode != 0:
                STATE["error"] = f"Loi (ma {proc.returncode}), xem log o tren."
                STATE["step"] = "idle"
                return
                
            STATE["step"] = "done"
            epub_path = f"{title}.epub"
            if os.path.isdir(SHARED_DOCUMENTS):
                try:
                    shutil.copy(epub_path, SHARED_DOCUMENTS)
                    STATE["epub"] = f"{epub_path} (da copy vao Documents)"
                except Exception as e:
                    STATE["epub"] = f"{epub_path} (Loi copy: {str(e)})"
            else:
                STATE["epub"] = epub_path
                
    except Exception as e:
        with LOCK:
            STATE["running"] = False
            STATE["error"] = f"Loi he thong: {str(e)}"
            STATE["step"] = "idle"
            CURRENT_PROC = None

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
        if self.path == "/stop":
            global CURRENT_PROC
            with LOCK:
                if STATE["running"] and CURRENT_PROC:
                    STATE["error"] = "Stopped"
                    try:
                        CURRENT_PROC.terminate()
                    except Exception:
                        pass
            self.send_response(204)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        params = urllib.parse.parse_qs(self.rfile.read(length).decode())
        
        input_val = params.get("input", [""])[0].strip()
        title = params.get("title", [""])[0].strip()
        author = params.get("author", [""])[0].strip()
        model = params.get("model", ["deepseek-v4-flash"])[0].strip()
        
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
        
        with LOCK:
            already_running = STATE["running"]
            
        if not already_running and input_val:
            threading.Thread(
                target=run_pipeline,
                args=(input_val, title, author, model, workers, temperature, allow_peak, no_style_detect, no_thinking),
                daemon=True
            ).start()
            
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # im lang, poll moi 1s spam terminal khong can thiet

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("GUI web: http://localhost:8000")
    http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
