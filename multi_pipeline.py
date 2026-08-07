"""
multi_pipeline.py - Chay nhieu truyen song song bang 1 lenh.

Doc danh sach truyen tu file JSON (--config), moi truyen chay trong 1 Thread rieng.
Chia se 1 Event dung chung (balance_empty_event): neu bat ky truyen nao gap loi
het so du API (InsufficientBalanceError / HTTP 402), tat ca truyen khac lap tuc
dung theo.

Su dung:
    # Tao file novels.json (vi du):
    # [
    #   {"raw": "truyen_A_raw.txt", "title": "Truyen A", "author": "Tac gia A"},
    #   {"raw": "truyen_B_raw.txt", "title": "Truyen B", "glossary": "glossary_B.json"}
    # ]
    #
    # Chay:
    #   .venv/bin/python multi_pipeline.py --config novels.json
    #   .venv/bin/python multi_pipeline.py --config novels.json --api-key sk-xxxx

Moi truyen ho tro cac khoa JSON sau (tuong duong tham so pipeline.py):
    raw, translated, title, author, epub, glossary,
    model, temperature, workers, style_detect, thinking, avoid_peak
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

_global_stop = False


def _handle_sigterm(signum, frame):
    global _global_stop
    _global_stop = True
    print("\n[DUNG] Nhan signal, dang dung tat ca sau chuong hien tai...")


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)

from build_epub import build_epub
from crawler import crawl_novel
from deepseek_translate import load_dotenv, translate_novel
from validator import validate_translation


def _make_prefixed_log(prefix: str):
    """Tao ham log co prefix [Truyen X] de phan biet khi chay song song."""
    lock = threading.Lock()

    def _log(msg: str):
        with lock:
            print(f"[{prefix}] {msg}", flush=True)

    return _log


def run_one_novel(cfg: dict, api_key: str, balance_empty_event: threading.Event,
                  result_slot: dict) -> None:
    """Chay toan bo pipeline cho 1 truyen. Duoc goi trong 1 Thread rieng."""
    title = cfg.get("title", "Unknown")
    log = _make_prefixed_log(title)

    raw_file = cfg.get("raw", "")
    translated_file = cfg.get("translated") or f"{raw_file}.viet.txt"
    epub_path = cfg.get("epub") or f"{title}.epub"
    glossary = cfg.get("glossary", "glossary.json")
    model = cfg.get("model", "deepseek-v4-flash")
    temperature = cfg.get("temperature", 1.3)
    workers = cfg.get("workers", 1)
    style_detect = cfg.get("style_detect", True)
    thinking = cfg.get("thinking", True)
    avoid_peak = cfg.get("avoid_peak", True)
    author = cfg.get("author", "Unknown")
    start_url = cfg.get("start_url")

    # Ket qua tra ve chia se voi thread chinh
    result_slot["title"] = title
    result_slot["status"] = "running"
    result_slot["failed"] = []

    def should_stop():
        return _global_stop or balance_empty_event.is_set()

    def on_balance_error(msg: str):
        log(f"\n{'='*60}")
        log(f"[!!! HET SO DU API !!!] {msg}")
        log(f"Tat ca truyen dang dich se dung lai ngay lap tuc.")
        log(f"{'='*60}")
        balance_empty_event.set()

    try:
        # Buoc 1: Cao truyen (neu co URL)
        log("=== Buoc 1/4: Cao truyen ===")
        if start_url:
            crawl_novel(start_url, raw_file, should_stop=should_stop)
        elif os.path.exists(raw_file):
            log(f"Bo qua cao - da co san {raw_file}.")
        else:
            log(f"Loi: khong co start_url va khong tim thay {raw_file}. Bo qua truyen nay.")
            result_slot["status"] = "error"
            return

        # Buoc 2: Dich
        log("=== Buoc 2/4: Dich bang DeepSeek API ===")
        failed = translate_novel(
            raw_file, translated_file, glossary, api_key,
            model=model, temperature=temperature, workers=workers,
            thinking=thinking, style_detect=style_detect,
            avoid_peak=avoid_peak, log=log,
            should_stop=should_stop,
            on_balance_error=on_balance_error,
        )
        result_slot["failed"] = failed or []

        if balance_empty_event.is_set():
            log("Dung do het so du API. Chay lai sau khi nap them token.")
            result_slot["status"] = "stopped_balance"
            return

        if should_stop():
            log("Dung theo yeu cau. Chay lai se tu tiep tuc.")
            result_slot["status"] = "stopped"
            return

        # Buoc 3: Validation
        log("=== Buoc 3/4: Kiem tra chat luong (Validation) ===")
        warnings = validate_translation(raw_file, translated_file, log=log)
        if warnings:
            log("[CANH BAO] Phat hien van de. Ban co the kiem tra lai truoc khi doc.")

        # Buoc 4: Dong goi EPUB
        log("=== Buoc 4/4: Dong goi EPUB ===")
        if failed:
            log(f"CANH BAO: {len(failed)} chuong dich that bai, EPUB se KHONG day du.")
        build_epub(translated_file, epub_path, title, author)
        log(f"Hoan tat! EPUB: {epub_path}")
        result_slot["status"] = "done"

    except Exception as e:
        log(f"LOI NGHIEM TRONG: {type(e).__name__}: {e}")
        result_slot["status"] = "error"
        result_slot["error"] = str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Dich nhieu truyen song song tu file config JSON."
    )
    parser.add_argument(
        "--config", required=True,
        help="Duong dan den file JSON chua danh sach truyen can dich."
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--api-key", default=None, help="DeepSeek API key (ghi de .env)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    # Doc config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Loi: khong tim thay file config '{args.config}'.")
        print("\nMau file novels.json:")
        print(json.dumps([
            {"raw": "truyen_A_raw.txt", "title": "Truyen A", "author": "Tac gia A"},
            {"raw": "truyen_B_raw.txt", "title": "Truyen B", "glossary": "glossary_B.json"},
        ], ensure_ascii=False, indent=2))
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        novel_list = json.load(f)

    if not novel_list:
        print("Danh sach truyen trong file config rong.")
        sys.exit(0)

    load_dotenv(args.env_file)
    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print(f"Loi: thieu DEEPSEEK_API_KEY (dat trong {args.env_file} hoac --api-key).")
        sys.exit(1)

    print(f"Bat dau dich {len(novel_list)} truyen song song...")
    print("-" * 60)

    # Event chia se bao hieu het so du API
    balance_empty_event = threading.Event()

    # Khoi chay tat ca truyen trong cac Thread rieng
    threads = []
    results = [{}] * len(novel_list)
    for i, cfg in enumerate(novel_list):
        results[i] = {}
        t = threading.Thread(
            target=run_one_novel,
            args=(cfg, api_key, balance_empty_event, results[i]),
            name=f"novel-{i}",
            daemon=True,
        )
        threads.append(t)
        t.start()

    # Cho tat ca hoan thanh
    for t in threads:
        t.join()

    # Tong ket
    print("\n" + "=" * 60)
    print("TONG KET KET QUA:")
    print("=" * 60)
    status_labels = {
        "done": "HOAN TAT",
        "stopped": "DA DUNG (resume khi chay lai)",
        "stopped_balance": "DUNG DO HET SO DU API",
        "error": "LOI",
        "running": "VAN DANG CHAY (?)  ",
    }
    for r in results:
        title = r.get("title", "?")
        status = r.get("status", "unknown")
        label = status_labels.get(status, status.upper())
        failed_count = len(r.get("failed", []))
        failed_note = f" | {failed_count} chuong that bai" if failed_count else ""
        print(f"  [{label}] {title}{failed_note}")
        if r.get("error"):
            print(f"          Chi tiet loi: {r['error']}")

    if balance_empty_event.is_set():
        print("\n[!] Tat ca truyen da dung do HET SO DU API.")
        print("    Vui long nap them token tai platform.deepseek.com roi chay lai.")
        print("    He thong se tu dong RESUME tu chuong chua dich.")


if __name__ == "__main__":
    main()
