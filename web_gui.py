"""web_gui.py - GUI web toi thieu (chi http.server chuan lib, khong Flask/Tkinter) de
chay pipeline.py (cao -> dich DeepSeek API -> dong goi EPUB) tu trinh duyet dien thoai.

Chay: python web_gui.py roi mo http://localhost:8000
"""
import http.server
import json
import os
import re
import subprocess
import threading
import traceback
import urllib.parse
import tempfile

import requests

from build_epub import build_epub
from crawler import guess_title
from deepseek_translate import (load_dotenv, TRANSLATE_SYSTEM_PROMPT,
                                call_deepseek, load_glossary, translate_chapter)
from output_storage import save_output_file
from text_postprocess import postprocess

# Load env variables on startup
load_dotenv()

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
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "Hi"}],
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


def test_translate_handler(chinese_text: str, api_key: str) -> dict:
    """Dich doan van Trung -> Viet va xuat EPUB de kiem tra toan bo pipeline."""
    global TEST_EPUB_PATH
    try:
        system_prompt = TRANSLATE_SYSTEM_PROMPT.format(style_guide_block="")
        chapter = {"title": "Chuong thu nhat", "paragraphs": [chinese_text]}
        glossary = load_glossary("glossary.json")
        translated = translate_chapter(chapter, glossary, system_prompt, api_key,
                                       model="deepseek-v4-flash", temperature=1.3,
                                       thinking=True)

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

            epub_file = "test_dung_thu.epub"
            build_epub(tmp.name, epub_file, "Truyen dung thu", "DeepSeek API")
            TEST_EPUB_PATH = os.path.abspath(epub_file)

            return {
                "success": True,
                "translated_text": "\n".join(translated["paragraphs"]),
                "epub_file": epub_file,
            }
        finally:
            os.unlink(tmp.name)

    except Exception as e:
        return {"success": False, "message": f"Loi dich thu: {e}", "detail": traceback.format_exc()}


# Trạng thái toàn cục để web cap nhat realtime
STATE = {
    "running": False,
    "log": "",
    "epub": None,           # co the la 1 path (EPUB) hoac chuoi liet ke ca EPUB + PDF
    "error": None,
    "step": "idle",          # "idle", "crawling", "translating", "packaging", "done"
    "current_chapter": 0,
    "total_chapters": 0,
    "stop_requested": False,  # dat truoc khi CURRENT_PROC ton tai van phai duoc ton trong
    "error_detail": "",       # traceback/duoi log day du de nguoi dung copy di fix
    "raw_file": "",           # file tho dang dung cho lan chay hien tai (de ro rang)
    "translated_file": ""
}
LOCK = threading.Lock()
CURRENT_PROC = None
TEST_EPUB_PATH = None  # duong dan file EPUB dung thu vua tao
UPLOAD_DIR = "uploads"  # noi luu file da cao nguoi dung chon tu may

PAGE = """<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
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
            padding-top: max(20px, env(safe-area-inset-top));
            padding-bottom: max(20px, env(safe-area-inset-bottom));
            padding-left: max(20px, env(safe-area-inset-left));
            padding-right: max(20px, env(safe-area-inset-right));
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
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal-overlay.active { display: flex; }
        .modal-box {
            background: #161c2d;
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 28px;
            width: 90%;
            max-width: 500px;
            max-height: 85vh;
            overflow-y: auto;
        }
        .modal-box h3 {
            margin-top: 0;
            font-size: 18px;
            color: var(--accent-cyan);
        }
        .modal-box textarea {
            width: 100%;
            min-height: 100px;
            background: rgba(10, 12, 22, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            padding: 10px;
            resize: vertical;
            font-family: inherit;
            box-sizing: border-box;
        }
        .modal-box textarea:focus {
            outline: none;
            border-color: var(--accent-cyan);
        }
        .modal-btn-row {
            display: flex;
            gap: 10px;
            margin-top: 14px;
        }
        .modal-btn {
            flex: 1;
            padding: 10px;
            border-radius: 8px;
            border: none;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
            font-family: inherit;
        }
        .modal-btn.primary { background: var(--btn-start-grad); color: #fff; }
        .modal-btn.secondary { background: rgba(255,255,255,0.08); color: #cbd5e1; border: 1px solid var(--glass-border); }
        .modal-result {
            margin-top: 14px;
            padding: 12px;
            border-radius: 8px;
            font-size: 13px;
            display: none;
            line-height: 1.6;
            word-break: break-word;
        }
        .modal-result.success {
            display: block;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #34d399;
        }
        .modal-result.error {
            display: block;
            background: rgba(244, 63, 94, 0.1);
            border: 1px solid rgba(244, 63, 94, 0.2);
            color: #f87171;
        }
        .modal-result a {
            color: var(--accent-cyan);
            text-decoration: underline;
        }

        /* ===== Mobile Portrait Optimizations ===== */
        .api-key-form {
            display: flex;
            gap: 10px;
            align-items: center;
            margin-top: 6px;
        }
        .api-key-form input {
            margin: 0;
            flex: 1;
            min-width: 0;
        }
        .api-key-actions {
            display: flex;
            gap: 8px;
            flex-shrink: 0;
        }
        .api-key-actions button {
            min-width: 0;
            flex: 0 0 auto;
        }
        .file-upload-row {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: -10px 0 16px 0;
        }
        .format-row {
            display: flex;
            gap: 8px;
            margin: 6px 0 16px 0;
            flex-wrap: wrap;
        }
        .format-opt {
            flex: 1 1 auto;
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
            background: rgba(10, 12, 22, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: var(--text-main);
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            margin: 0;
            min-width: 0;
        }
        .format-opt em {
            color: var(--text-muted);
            font-style: normal;
            font-size: 11px;
        }
        .format-opt input[type="radio"] {
            width: 16px;
            height: 16px;
            margin: 0;
            accent-color: var(--accent-cyan);
            flex-shrink: 0;
        }
        .format-opt:has(input:checked) {
            border-color: var(--accent-cyan);
            background: rgba(0, 242, 254, 0.08);
            box-shadow: 0 0 8px rgba(0, 242, 254, 0.15);
        }
        .checkbox-group input[type="checkbox"] {
            min-width: 18px;
            min-height: 18px;
        }

        @media (max-width: 480px) {
            body {
                padding: 12px;
                padding-top: max(12px, env(safe-area-inset-top));
                padding-bottom: max(12px, env(safe-area-inset-bottom));
            }
            .container {
                margin: 8px auto;
                padding: 18px 14px;
                border-radius: 14px;
            }
            h2 {
                font-size: 22px;
                margin-bottom: 16px;
            }
            .subtitle {
                font-size: 12px;
                margin-top: -14px;
                margin-bottom: 20px;
            }
            label {
                font-size: 13px;
                margin-top: 10px;
            }
            input, select {
                padding: 11px 14px;
                font-size: 14px;
                border-radius: 8px;
            }
            button {
                padding: 13px;
                font-size: 15px;
                min-height: 44px;
            }
            .api-key-form {
                flex-direction: column;
                align-items: stretch;
            }
            .api-key-actions {
                flex-wrap: wrap;
            }
            .api-key-actions button {
                flex: 1 1 calc(50% - 4px);
                min-height: 44px;
                padding: 11px 8px;
                font-size: 13px;
            }
            .file-upload-row {
                flex-direction: column;
                align-items: flex-start;
                gap: 6px;
            }
            .advanced-grid {
                grid-template-columns: 1fr;
                gap: 12px;
                padding: 12px;
            }
            .col-span-2 {
                grid-column: span 1;
            }
            .btn-group {
                gap: 8px;
                margin-top: 16px;
            }
            .btn-group button {
                padding: 13px;
            }
            .steps {
                margin: 18px 0;
            }
            .step {
                font-size: 10px;
            }
            .step-dot {
                width: 28px;
                height: 28px;
                font-size: 12px;
                margin-bottom: 6px;
            }
            pre {
                padding: 12px;
                font-size: 11px;
                max-height: 200px;
                border-radius: 10px;
            }
            .modal-overlay {
                align-items: flex-end;
            }
            .modal-box {
                width: 100%;
                max-width: 100%;
                border-radius: 16px 16px 0 0;
                max-height: 80vh;
                padding: 20px 16px;
                padding-bottom: max(20px, env(safe-area-inset-bottom));
            }
            .modal-box h3 {
                font-size: 16px;
            }
            .modal-box textarea {
                min-height: 80px;
                font-size: 14px;
            }
            .modal-btn {
                padding: 12px;
                min-height: 44px;
                font-size: 14px;
            }
            .result-box {
                font-size: 13px;
                padding: 12px;
                border-radius: 8px;
            }
            .console-header {
                margin-top: 20px;
            }
            .error-report pre {
                max-height: 150px;
            }
        }

        @media (max-width: 360px) {
            .container {
                margin: 4px auto;
                padding: 14px 10px;
            }
            h2 {
                font-size: 20px;
            }
            .api-key-actions button {
                flex: 1 1 100%;
            }
            .step {
                font-size: 9px;
            }
            .step-dot {
                width: 24px;
                height: 24px;
                font-size: 11px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>DỊCH TRUYỆN NOVEL</h2>
        <div class="subtitle">Hệ thống dịch thuật tự động sử dụng DeepSeek API</div>
        
        <div id="key-warning" class="result-box error" style="display: none; margin-top: 0; margin-bottom: 20px; font-weight: normal; text-align: left;">
            ⚠️ <strong>Thiếu DEEPSEEK_API_KEY:</strong> Vui lòng nhập API Key xuống ô bên dưới và nhấn <strong>Lưu Key</strong> để bắt đầu sử dụng dịch thuật DeepSeek.
        </div>

        <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--glass-border); padding: 16px; border-radius: 12px; margin-bottom: 24px;">
            <label style="margin-top: 0;">DeepSeek API Key (sk-...):</label>
            <form onsubmit="return false;" class="api-key-form">
                <input type="password" autocomplete="off" id="api_key_input" placeholder="Nhập sk-...">
                <div class="api-key-actions">
                    <button type="button" id="btn-save-key" style="background: var(--btn-start-grad); color: white; border-radius: 10px; font-weight: 700; border: none; cursor: pointer;">Lưu Key</button>
                    <button type="button" id="btn-test-key" style="background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); color: white; border-radius: 10px; font-weight: 700; cursor: pointer; transition: all 0.2s;">Test Key</button>
                    <button type="button" id="btn-test-translate" style="background: rgba(0, 242, 254, 0.1); border: 1px solid rgba(0, 242, 254, 0.3); color: var(--accent-cyan); border-radius: 10px; font-weight: 700; cursor: pointer; transition: all 0.2s;">Dịch thử</button>
                </div>
            </form>
            <div style="display:flex; align-items:center; gap:8px; margin-top: 8px;">
                <div id="key-status" style="font-size: 12px; color: var(--text-muted); flex:1;">Đang kiểm tra API Key...</div>
                <button type="button" id="btn-copy-key-error" class="console-btn" style="display:none; flex:0 0 auto;">📋 Copy lỗi</button>
            </div>
        </div>
        
        <form id="f">
            <label>Nguồn truyện:</label>
            <input name="input" id="input_source" placeholder="URL chương 1 (ví dụ: ..._1.html) hoặc đường dẫn file .txt thô" required>
            <div class="file-upload-row">
                <label for="raw_file_input" style="margin:0; flex:0 0 auto; font-weight:500; font-size:13px; color:var(--text-muted); cursor:pointer; text-decoration:underline;">Hoặc chọn file đã cào sẵn từ máy...</label>
                <input type="file" id="raw_file_input" accept=".txt,text/plain" style="display:none;">
            </div>
            <div id="raw_file_status" style="font-size:12px; margin: -12px 0 16px 0; color: var(--text-muted); display:none;"></div>

            <label>Tên truyện (để trống sẽ tự đoán từ URL):</label>
            <input name="title" placeholder="Ví dụ: Đệ Tam Trùng Nhân Cách">

            <label>Định dạng xuất:</label>
            <div class="format-row">
                <label class="format-opt">
                    <input type="radio" name="formats" value="epub" checked>
                    <span>EPUB <em>(khuyên dùng)</em></span>
                </label>
                <label class="format-opt">
                    <input type="radio" name="formats" value="pdf">
                    <span>PDF <em>(phòng hờ)</em></span>
                </label>
                <label class="format-opt">
                    <input type="radio" name="formats" value="both">
                    <span>Cả EPUB &amp; PDF</span>
                </label>
            </div>

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

                    <div class="col-span-2" style="background: rgba(0,242,254,0.04); border: 1px solid rgba(0,242,254,0.15); border-radius: 10px; padding: 12px 14px; margin-bottom:4px;">
                        <div class="checkbox-group" style="margin-bottom:4px;">
                            <input type="checkbox" name="stream_mode" id="stream_mode">
                            <label for="stream_mode" style="display:inline;margin:0;font-weight:600;color:var(--accent-cyan);">⚡ Stream Mode: Cào xong chương nào, dịch ngay chương đó</label>
                        </div>
                        <p style="font-size:12px; color:var(--text-muted); margin: 4px 0 8px 16px;">Không cần chờ cào hết toàn bộ truyện. Phù hợp khi muốn đọc sớm.</p>
                        <div id="stream-chapters-row" style="display:none; align-items:center; gap:10px; margin-left:16px;">
                            <label style="margin:0; font-size:13px; white-space:nowrap;">Giới hạn số chương:</label>
                            <input type="number" name="chapters" id="chapters_input" min="1" max="9999" value="20" style="margin:0; width:90px; flex:0 0 auto;">
                            <span style="font-size:12px; color:var(--text-muted);">(0 = toàn bộ)</span>
                        </div>
                    </div>

                    <div class="col-span-2">
                        <div class="checkbox-group">
                            <input type="checkbox" name="allow_peak" id="allow_peak">
                            <label for="allow_peak" style="display:inline;margin:0;font-weight:normal;">Cho phép dịch trong giờ cao điểm (Giá gấp đôi)</label>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" name="no_style_detect" id="no_style_detect">
                            <label for="no_style_detect" style="display:inline;margin:0;font-weight:normal;">Không tự động phân tích văn phong (nhiều chương)</label>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" name="no_thinking" id="no_thinking">
                            <label for="no_thinking" style="display:inline;margin:0;font-weight:normal;">Tắt Thinking Mode (Không khuyến khích - có thể gây lỗi dịch)</label>
                        </div>
                    </div>
                </div>
            </details>
            
            <details>
                <summary>💡 Hướng dẫn Termux & Khắc phục sự cố</summary>
                <div style="padding: 16px; border-top: 1px solid rgba(255, 255, 255, 0.05); background: rgba(0, 0, 0, 0.15); font-size: 13px; line-height: 1.6; color: var(--text-main);">
                    <div style="margin-bottom: 12px;">
                        <strong style="color: var(--accent-cyan);">⏯️ Tự động khôi phục (Resume):</strong>
                        <p style="margin: 4px 0 0 0; color: var(--text-muted);">Hệ thống hỗ trợ resume tự động. Nếu cào/dịch bị dừng giữa chừng (mất mạng, tắt app...), bạn chỉ cần nhập lại thông tin cũ và chạy lại, tiến trình sẽ tự động tiếp tục từ chương dang dở.</p>
                    </div>
                    <div style="margin-bottom: 12px;">
                        <strong style="color: var(--accent-cyan);">🔍 Kiểm tra tiến trình chạy ẩn:</strong>
                        <p style="margin: 4px 0 0 0; color: var(--text-muted);">Mở cửa sổ Termux mới và nhập lệnh để kiểm tra xem Python có chạy ẩn không:</p>
                        <code style="display:block; background:#060810; padding:6px 10px; border-radius:6px; margin:4px 0; color:#38bdf8; font-family:monospace;">ps -ef | grep python</code>
                        <p style="margin: 4px 0 0 0; color: var(--text-muted);">Xem nhật ký log chương mới nhất:</p>
                        <code style="display:block; background:#060810; padding:6px 10px; border-radius:6px; margin:4px 0; color:#38bdf8; font-family:monospace;">tail -n 20 ~/novel/pipeline_*.log</code>
                        <p style="margin: 4px 0 0 0; color: var(--text-muted);">Tắt cưỡng bức tiến trình chạy ẩn:</p>
                        <code style="display:block; background:#060810; padding:6px 10px; border-radius:6px; margin:4px 0; color:#38bdf8; font-family:monospace;">pkill -f python</code>
                    </div>
                    <div>
                        <strong style="color: var(--accent-cyan);">📁 Vị trí lưu file & Lấy sách EPUB:</strong>
                        <p style="margin: 4px 0 0 0; color: var(--text-muted);">Mọi file lưu trong thư mục <code style="color:#e2e8f0; font-family:monospace;">~/novel</code>. Để đưa file EPUB ra thư mục Download của điện thoại, nhập lệnh:</p>
                        <code style="display:block; background:#060810; padding:6px 10px; border-radius:6px; margin:4px 0; color:#38bdf8; font-family:monospace;">cp ~/novel/*.epub /sdcard/Download/</code>
                    </div>
                </div>
            </details>
            
            <div class="btn-group">
                <button type="submit" id="btn-start">Bắt đầu dịch</button>
                <button type="button" id="btn-stop">Dừng lại</button>
            </div>
        </form>
        
        <div class="steps" id="step-indicator">
            <div class="step" id="step-crawl">
                <div class="step-dot">1</div>
                Cào truyện
            </div>
            <div class="step" id="step-translate">
                <div class="step-dot">2</div>
                Dịch thuật
            </div>
            <div class="step" id="step-validate">
                <div class="step-dot">3</div>
                Kiểm tra
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
            <div id="file-info" style="font-size:11px; color:var(--text-muted); margin-top:8px; font-family:'Fira Code', monospace; word-break:break-all;"></div>
        </div>

        <div class="result-box" id="result"></div>

        <div class="error-report" id="error-report" style="display:none; margin-top:12px; padding:14px; border-radius:10px; background:rgba(244,63,94,0.06); border:1px solid rgba(244,63,94,0.25);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:12px; font-weight:700; color:var(--accent-red);">CHI TIẾT LỖI</span>
                <button class="console-btn" id="btn-copy-error">📋 Copy báo cáo lỗi</button>
            </div>
            <pre id="error-detail-text" style="max-height:180px; color:#fca5a5;"></pre>
        </div>

        <div class="console-header">
            <span>CONSOLE LOGS</span>
            <div class="console-controls">
                <button class="console-btn active" id="btn-scroll">Auto Scroll: ON</button>
                <button class="console-btn" id="btn-copy">Copy Logs</button>
            </div>
        </div>
        <pre id="log"></pre>
    </div>
    
    <div class="modal-overlay" id="test-modal">
        <div class="modal-box">
            <h3>Dịch thử đoạn văn</h3>
            <p style="font-size:13px; color:var(--text-muted); margin-top:0;">Nhập đoạn văn Trung Quốc ngắn, hệ thống sẽ dịch sang Việt và xuất file EPUB để kiểm tra.</p>
            <textarea id="test-text" placeholder="Nhập văn bản tiếng Trung...">叶秋坐在电脑前，看着屏幕上闪烁的光标，手指轻轻敲击着键盘。窗外的阳光透过窗帘的缝隙洒进来，在地板上画出一道金色的光线。他深吸一口气，开始敲下第一行字。</textarea>
            <div class="modal-btn-row">
                <button class="modal-btn primary" id="btn-run-test">Dịch &amp; tạo EPUB</button>
                <button class="modal-btn secondary" id="btn-close-modal">Đóng</button>
            </div>
            <div class="modal-result" id="test-result"></div>
            <button class="console-btn" id="btn-copy-test-error" style="display:none; margin-top:10px;">📋 Copy lỗi để fix</button>
        </div>
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
        const fileInfo = document.getElementById('file-info');
        const errorReport = document.getElementById('error-report');
        const errorDetailText = document.getElementById('error-detail-text');
        const btnCopyError = document.getElementById('btn-copy-error');
        let lastStatus = {};

        function copyWithFeedback(btn, text) {
            navigator.clipboard.writeText(text);
            const original = btn.textContent;
            btn.textContent = 'Đã copy!';
            setTimeout(() => btn.textContent = original, 1500);
        }

        btnCopyError.onclick = () => {
            const report = [
                `Bước lỗi: ${lastStatus.step || '(không rõ)'}`,
                `Lỗi: ${lastStatus.error || '(không rõ)'}`,
                `File thô: ${lastStatus.raw_file || '(không có)'}`,
                '',
                'Chi tiết (log/traceback):',
                lastStatus.error_detail || '(không có)'
            ].join('\\n');
            copyWithFeedback(btnCopyError, report);
        };

        let autoScroll = true;
        let pollTimeout = null;
        
        const apiKeyInput = document.getElementById('api_key_input');
        const btnSaveKey = document.getElementById('btn-save-key');
        const btnTestKey = document.getElementById('btn-test-key');
        const keyStatus = document.getElementById('key-status');
        const keyWarning = document.getElementById('key-warning');
        const btnCopyKeyError = document.getElementById('btn-copy-key-error');
        let lastKeyError = '';

        function setKeyStatus(ok, message) {
            keyStatus.textContent = (ok ? "✓ " : "✗ ") + message;
            keyStatus.style.color = ok ? "var(--accent-green)" : "var(--accent-red)";
            lastKeyError = ok ? '' : message;
            btnCopyKeyError.style.display = ok ? 'none' : 'inline-block';
        }

        btnCopyKeyError.onclick = () => copyWithFeedback(btnCopyKeyError, lastKeyError);

        btnTestKey.onclick = async () => {
            const key = apiKeyInput.value.trim();
            if (!key) {
                alert("Vui lòng nhập API Key trước khi test.");
                return;
            }
            btnTestKey.disabled = true;
            btnTestKey.textContent = "Đang test...";
            setKeyStatus(true, "Đang kết nối tới DeepSeek API để kiểm tra...");
            keyStatus.style.color = "var(--text-muted)";

            try {
                const params = new URLSearchParams();
                params.append("key", key);
                const r = await fetch('/test_key', { method: 'POST', body: params });
                const data = await r.json();
                setKeyStatus(data.success, data.message);
            } catch (err) {
                console.error(err);
                setKeyStatus(false, "Lỗi kết nối khi kiểm tra Key: " + err.message);
            } finally {
                btnTestKey.disabled = false;
                btnTestKey.textContent = "Test Key";
            }
        };

        btnSaveKey.onclick = async () => {
            const key = apiKeyInput.value.trim();
            if (!key) {
                alert("Vui lòng nhập API Key.");
                return;
            }
            btnSaveKey.disabled = true;
            btnSaveKey.textContent = "Đang lưu...";
            try {
                const params = new URLSearchParams();
                params.append("key", key);
                const r = await fetch('/save_key', { method: 'POST', body: params });
                if (r.ok) {
                    setKeyStatus(true, "Đã lưu API Key thành công!");
                    keyWarning.style.display = "none";
                } else {
                    setKeyStatus(false, "Không thể lưu API Key.");
                }
            } catch (err) {
                console.error(err);
                setKeyStatus(false, "Lỗi kết nối khi lưu: " + err.message);
            } finally {
                btnSaveKey.disabled = false;
                btnSaveKey.textContent = "Lưu Key";
            }
        };

        async function checkKey() {
            try {
                const r = await fetch('/get_key');
                const data = await r.json();
                if (data.key) {
                    apiKeyInput.value = data.key;
                    keyStatus.textContent = "✓ Đã nạp API Key từ hệ thống.";
                    keyStatus.style.color = "var(--accent-green)";
                    keyWarning.style.display = "none";
                } else {
                    keyStatus.textContent = "✗ Chưa cấu hình API Key (chưa có trong .env)";
                    keyStatus.style.color = "var(--accent-red)";
                    keyWarning.style.display = "block";
                }
            } catch (err) {
                console.error("Check key error:", err);
            }
        }
        checkKey();

        const rawFileInput = document.getElementById('raw_file_input');
        const rawFileStatus = document.getElementById('raw_file_status');
        const inputSource = document.getElementById('input_source');

        rawFileInput.onchange = async () => {
            const file = rawFileInput.files[0];
            if (!file) return;
            rawFileStatus.style.display = 'block';
            rawFileStatus.textContent = 'Đang tải file lên...';
            rawFileStatus.style.color = 'var(--text-muted)';
            try {
                const text = await file.text();
                const r = await fetch('/upload_raw?name=' + encodeURIComponent(file.name), {
                    method: 'POST', body: text
                });
                const data = await r.json();
                if (data.success) {
                    inputSource.value = data.path;
                    rawFileStatus.textContent = '✓ Đã chọn file: ' + data.path;
                    rawFileStatus.style.color = 'var(--accent-green)';
                } else {
                    rawFileStatus.textContent = '✗ ' + (data.message || 'Lỗi tải file.');
                    rawFileStatus.style.color = 'var(--accent-red)';
                }
            } catch (err) {
                rawFileStatus.textContent = '✗ Lỗi tải file: ' + err.message;
                rawFileStatus.style.color = 'var(--accent-red)';
            }
        };

        const testModal = document.getElementById('test-modal');
        const btnTestTranslate = document.getElementById('btn-test-translate');
        const btnRunTest = document.getElementById('btn-run-test');
        const btnCloseModal = document.getElementById('btn-close-modal');
        const testText = document.getElementById('test-text');
        const testResult = document.getElementById('test-result');
        const btnCopyTestError = document.getElementById('btn-copy-test-error');
        let lastTestError = '';

        btnTestTranslate.onclick = () => {
            testModal.classList.add('active');
            testResult.className = 'modal-result';
            btnCopyTestError.style.display = 'none';
        };

        btnCopyTestError.onclick = () => copyWithFeedback(btnCopyTestError, lastTestError);

        btnCloseModal.onclick = () => {
            testModal.classList.remove('active');
        };

        testModal.onclick = (e) => {
            if (e.target === testModal) testModal.classList.remove('active');
        };

        btnRunTest.onclick = async () => {
            const text = testText.value.trim();
            if (!text) {
                alert("Vui lòng nhập đoạn văn bản tiếng Trung.");
                return;
            }
            btnRunTest.disabled = true;
            btnRunTest.textContent = "Đang dịch...";
            testResult.className = 'modal-result';

            try {
                const params = new URLSearchParams();
                params.append("text", text);
                const r = await fetch('/test_translate', { method: 'POST', body: params });
                const data = await r.json();
                if (data.success) {
                    testResult.innerHTML = "✓ <strong>Dịch thành công!</strong><br><br>"
                        + "<em>" + data.translated_text.substring(0, 300) + (data.translated_text.length > 300 ? "..." : "") + "</em><br><br>"
                        + '<a href="/download_test" download>📥 Tải file EPUB</a>';
                    testResult.className = 'modal-result success';
                    btnCopyTestError.style.display = 'none';
                } else {
                    testResult.textContent = "✗ " + data.message;
                    testResult.className = 'modal-result error';
                    lastTestError = data.message + (data.detail ? "\\n\\n" + data.detail : "");
                    btnCopyTestError.style.display = 'inline-block';
                }
            } catch (err) {
                testResult.textContent = "✗ Lỗi kết nối: " + err.message;
                testResult.className = 'modal-result error';
                lastTestError = "Lỗi kết nối: " + err.message;
                btnCopyTestError.style.display = 'inline-block';
            } finally {
                btnRunTest.disabled = false;
                btnRunTest.textContent = "Dịch & tạo EPUB";
            }
        };

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
        
        // Stream Mode toggle
        const streamModeCheck = document.getElementById('stream_mode');
        const streamChaptersRow = document.getElementById('stream-chapters-row');
        streamModeCheck.onchange = () => {
            streamChaptersRow.style.display = streamModeCheck.checked ? 'flex' : 'none';
        };

        function updateSteps(currentStep, isStream) {
            const steps = isStream
                ? ['streaming', 'streaming', 'validating', 'done']
                : ['crawling', 'translating', 'validating', 'done'];
            const stepIds = [
                'step-crawl', 'step-translate', 'step-validate', 'step-done'
            ];
            const stateToIdx = isStream
                ? { 'streaming': 0, 'validating': 2, 'packaging': 2, 'done': 3 }
                : { 'crawling': 0, 'translating': 1, 'validating': 2, 'packaging': 2, 'done': 3 };

            // Reset stream label
            const crawlDot = document.querySelector('#step-crawl .step-dot');
            const crawlLabel = document.querySelector('#step-crawl');
            const translateDot = document.querySelector('#step-translate .step-dot');

            if (isStream) {
                document.querySelector('#step-crawl').lastChild.textContent = ' ⚡ Stream';
                document.querySelector('#step-translate').lastChild.textContent = ' Cào+Dịch';
            } else {
                document.querySelector('#step-crawl').lastChild.textContent = ' Cào truyện';
                document.querySelector('#step-translate').lastChild.textContent = ' Dịch thuật';
            }

            stepIds.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.className = 'step';
            });

            if (currentStep === 'idle') return;

            const activeIdx = stateToIdx[currentStep] ?? -1;
            stepIds.forEach((id, idx) => {
                const el = document.getElementById(id);
                if (!el) return;
                if (idx < activeIdx) el.className = 'step completed';
                else if (idx === activeIdx) el.className = 'step active';
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
                
                updateSteps(s.step, s.stream_mode);
                
                if (s.running && (s.step === 'crawling' || s.step === 'translating' || s.step === 'streaming')) {
                    progressArea.style.display = 'block';
                    if (s.step === 'crawling') {
                        progressText.textContent = `Đang cào chương: ${s.current_chapter}`;
                        progressBar.style.width = '100%';
                        progressPercent.textContent = 'Đang tải...';
                    } else if (s.step === 'streaming') {
                        progressText.textContent = `⚡ Stream: đã cào+dịch ${s.current_chapter} chương` + (s.total_chapters > 0 ? `/${s.total_chapters}` : '');
                        const pct = s.total_chapters > 0 ? Math.round(s.current_chapter / s.total_chapters * 100) : 50;
                        progressBar.style.width = `${Math.min(pct,100)}%`;
                        progressPercent.textContent = s.total_chapters > 0 ? `${pct}%` : 'Đang stream...';
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

                fileInfo.textContent = s.raw_file
                    ? `File thô: ${s.raw_file}  •  File dịch: ${s.translated_file}`
                    : '';

                if (s.epub) {
                    const lines = String(s.epub).split('\\n').filter(Boolean);
                    if (lines.length > 1) {
                        resultEl.innerHTML = 'Thành công! Các file đã lưu:<br>'
                            + lines.map(l => '• <code>' + l.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])) + '</code>').join('<br>');
                    } else {
                        resultEl.textContent = 'Thành công! File lưu tại: ' + s.epub;
                    }
                    resultEl.className = 'result-box success';
                } else if (s.error) {
                    resultEl.textContent = 'Lỗi: ' + s.error;
                    resultEl.className = 'result-box error';
                } else {
                    resultEl.style.display = 'none';
                }

                lastStatus = s;
                if (s.error_detail) {
                    errorReport.style.display = 'block';
                    errorDetailText.textContent = s.error_detail;
                } else {
                    errorReport.style.display = 'none';
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


def run_pipeline(input_val, title, author="", model="deepseek-v4-flash", workers=1, temperature=1.3, allow_peak=False, no_style_detect=False, no_thinking=False, formats="epub", stream_mode=False, chapters=0):
    title = title or guess_title(input_val)
    # -u: khong buffer stdout cua tien trinh con - neu khong, print() trong
    # crawler.py/pipeline.py bi block-buffer (khong phai tty) nen log/tien do
    # tren GUI dung im (giong "treo") hang chuc chuong roi moi hien 1 luc.
    import sys
    if formats not in ("epub", "pdf", "both"):
        formats = "epub"
    args = [sys.executable, "-u", "pipeline.py", "--title", title, "--formats", formats,
            # Web GUI tu di chuyen ket qua sau khi pipeline xong -> tat luu tu dong
            # trong pipeline.py de tranh copy 2 lan (pipeline ghi thang vao Documents
            # roi lam mat file goc, GUI khong tim thay khi copy lai).
            "--no-to-documents"]
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
    if stream_mode:
        args += ["--stream"]
        if chapters > 0:
            args += ["--chapters", str(chapters)]

    if input_val.startswith("http"):
        # File tho mac dinh cua pipeline.py la 1 ten CO DINH dung chung cho moi
        # truyen - khong dat --raw rieng se khien 2 truyen khac nhau cao/resume
        # chung vao 1 file, lam hong ca hai. Dat theo ten truyen de moi truyen
        # co file rieng va tu resume dung truyen cua chinh no.
        raw_file = f"{sanitize_filename(title)}_raw.txt"
        args += ["--start-url", input_val, "--raw", raw_file]
    else:
        raw_file = input_val
        args += ["--raw", raw_file]
    translated_file = f"{raw_file}.viet.txt"

    global CURRENT_PROC
    with LOCK:
        STATE.update(
            running=True,
            log="",
            epub=None,
            error=None,
            error_detail="",
            step="streaming" if stream_mode else "crawling",
            current_chapter=0,
            total_chapters=chapters if stream_mode and chapters > 0 else 0,
            stop_requested=False,
            stream_mode=stream_mode,
            raw_file=raw_file,
            translated_file=translated_file
        )

    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8", errors="replace")
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
                return
                
            STATE["step"] = "done"
            # pipeline.py sinh EPUB va/hoac PDF trong CWD (co the ca hai neu formats=both).
            # web_gui goi save_output_file() de di chuyen tung file sang thu muc user-visible
            # (~/storage/shared/Documents/DichTruyen tren Termux, ~/Documents/DichTruyen tren PC).
            # Da chan --no-to-documents ben run_pipeline nen pipeline khong copy trung.
            candidate_files = [f"{title}.epub", f"{title}.pdf"]
            saved_lines = []
            for cand in candidate_files:
                if not os.path.exists(cand):
                    continue
                try:
                    final_path, warn = save_output_file(cand, move=True)
                    if warn:
                        saved_lines.append(f"{cand} (giu tam o day - {warn})")
                    else:
                        saved_lines.append(final_path)
                except Exception as e:
                    saved_lines.append(f"{cand} (Loi luu: {e})")
            STATE["epub"] = "\n".join(saved_lines) if saved_lines else "(khong tim thay file dau ra)"
                
    except Exception as e:
        with LOCK:
            STATE["running"] = False
            STATE["error"] = f"Loi he thong: {e}"
            STATE["error_detail"] = traceback.format_exc()
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
        elif self.path == "/get_key":
            key = os.environ.get("DEEPSEEK_API_KEY", "")
            body = json.dumps({"key": key}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/download_test":
            if TEST_EPUB_PATH and os.path.exists(TEST_EPUB_PATH):
                with open(TEST_EPUB_PATH, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/epub+zip")
                self.send_header("Content-Disposition",
                                 'attachment; filename="test_dung_thu.epub"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Chua co file EPUB dung thu"}).encode())
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith("/upload_raw"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            filename = sanitize_filename(os.path.basename(qs.get("name", [""])[0]) or "cao_tay.txt")
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            save_path = os.path.join(UPLOAD_DIR, filename)
            with open(save_path, "wb") as out:
                out.write(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "path": save_path}, ensure_ascii=False).encode("utf-8"))
            return

        if self.path == "/stop":
            global CURRENT_PROC
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
            self.send_response(204)
            self.end_headers()
            return

        if self.path == "/save_key":
            length = int(self.headers.get("Content-Length", 0))
            params = urllib.parse.parse_qs(self.rfile.read(length).decode())
            key = params.get("key", [""])[0].strip()
            save_api_key(key)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode())
            return

        if self.path == "/test_key":
            length = int(self.headers.get("Content-Length", 0))
            params = urllib.parse.parse_qs(self.rfile.read(length).decode())
            key = params.get("key", [""])[0].strip()
            success, msg = test_deepseek_key(key)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": msg}).encode())
            return

        if self.path == "/test_translate":
            length = int(self.headers.get("Content-Length", 0))
            params = urllib.parse.parse_qs(self.rfile.read(length).decode())
            chinese_text = params.get("text", [""])[0].strip()
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                result = {"success": False, "message": "Chua co API Key. Vui long luu Key truoc."}
            elif not chinese_text:
                result = {"success": False, "message": "Vui long nhap doan van Trung."}
            else:
                result = test_translate_handler(chinese_text, api_key)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
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
        formats = params.get("formats", ["epub"])[0].strip() or "epub"
        if formats not in ("epub", "pdf", "both"):
            formats = "epub"
        stream_mode = "stream_mode" in params

        try:
            chapters = int(params.get("chapters", ["0"])[0].strip())
        except ValueError:
            chapters = 0

        with LOCK:
            already_running = STATE["running"]

        if not already_running and input_val:
            threading.Thread(
                target=run_pipeline,
                args=(input_val, title, author, model, workers, temperature, allow_peak, no_style_detect, no_thinking, formats, stream_mode, chapters),
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
