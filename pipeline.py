"""
pipeline.py - Chay ca quy trinh bang 1 lenh: Cao truyen -> Dich (DeepSeek API,
prompt toi uu + glossary) -> Dong goi EPUB tieng Viet.

Gop crawler.py + deepseek_translate.py + build_epub.py bang cach goi thang ham
cua tung file (khong subprocess, khong trung logic).

Su dung:
    # .env: DEEPSEEK_API_KEY=sk-xxxx
    # PC (Windows):
    .venv\\Scripts\\python pipeline.py \\
        --start-url "https://example.com/chuong-1.html" \\
        --title "Ten Truyen" --author "Tac gia"
    # Mobile (Termux) / Linux / macOS:
    .venv/bin/python pipeline.py \\
        --start-url "https://example.com/chuong-1.html" \\
        --title "Ten Truyen" --author "Tac gia"

Da co san file tho (vd da cao truoc do) thi bo --start-url, chi truyen --raw:
    python pipeline.py --raw truyen_da_cao.txt --ten "Ten Truyen"

Chay lai lenh cu se tu resume: bo qua chuong da cao (crawler noi tiep tu cuoi file
raw neu dung lai --start-url tro ve chuong 1) va bo qua chuong da dich (dua vao so
chuong da co trong --translated).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

_stop_flag = False


def _handle_sigterm(signum, frame):
    global _stop_flag
    _stop_flag = True
    print("\n[DUNG] Nhan SIGTERM, dang dung sau chuong hien tai...")


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)

from build_epub import build_epub
from crawler import DEFAULT_OUTPUT, crawl_novel, crawl_chapters_stream
from deepseek_translate import load_dotenv, translate_novel, translate_novel_stream, detect_style_guide
from validator import validate_translation


def main():
    parser = argparse.ArgumentParser(description="Quy trinh: Cao -> Dich DeepSeek -> Validate -> Dong goi EPUB")
    parser.add_argument("--start-url", default=None,
                         help="URL chuong 1 de cao (bo qua neu da co san --raw)")
    parser.add_argument("--raw", default=DEFAULT_OUTPUT, help="File luu noi dung tho da cao")
    parser.add_argument("--translated", default=None,
                         help="File luu ban dich, mac dinh <raw>.viet.txt")
    parser.add_argument("--title", required=True, help="Ten truyen (EPUB metadata + ten file EPUB)")
    parser.add_argument("--author", default="Unknown")
    parser.add_argument("--epub", default=None, help="Duong dan EPUB dau ra, mac dinh <title>.epub")
    parser.add_argument("--glossary", default="glossary.json")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--temperature", type=float, default=1.3)
    parser.add_argument("--workers", type=int, default=1,
                         help="So chuong dich song song (>1 danh doi tinh nhat quan ten rieng lay toc do)")
    parser.add_argument("--chapters", type=int, default=0,
                         help="Gioi han so chuong can cao/dich (0 = toan bo truyen). Dung voi --stream.")
    parser.add_argument("--stream", action="store_true",
                         help="[MOI] Che do stream: cao tung chuong roi dich ngay lap tuc, "
                              "khong cho den khi cao het. Nen dung kem --chapters X.")
    parser.add_argument("--no-style-detect", action="store_true")
    parser.add_argument("--no-thinking", action="store_true",
                         help="CANH BAO: tat thinking khien deepseek-v4-flash chi echo nguyen van "
                              "dau vao, KHONG dich - xem comment trong deepseek_translate.py")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--allow-peak", action="store_true",
                         help="Cho phep goi API trong gio cao diem DeepSeek (gia gap doi) - mac dinh khong cho phep")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    translated_file = args.translated or f"{args.raw}.viet.txt"

    load_dotenv(args.env_file)
    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print(f"Error: thieu DEEPSEEK_API_KEY (dat trong {args.env_file}, bien moi truong, hoac --api-key).")
        sys.exit(1)

    print("=== Buoc 1/4: Cao truyen ===")
    if args.stream and args.start_url:
        # --- CHE DO STREAM: cao tung chuong va dich ngay ---
        chapter_limit = args.chapters
        limit_msg = f" ({chapter_limit} chuong dau)" if chapter_limit > 0 else " (toan bo)"
        print(f"[STREAM MODE] Cao + Dich dong thoi{limit_msg}...")

        # Phan tich van phong truoc (lay 1 chuong mau de goi style detect)
        style_guide = ""
        if not args.no_style_detect:
            print("Dang lay mau van phong tu chuong dau...")
            from crawler import crawl_chapter, guess_title
            import re as _re
            match = _re.match(r"(.*_)(\d+)(\.html)$", args.start_url)
            if match:
                sample_ch = crawl_chapter(args.start_url)
                if sample_ch:
                    style_guide = detect_style_guide([sample_ch], api_key, args.model,
                                                      should_stop=lambda: _stop_flag)
                    if style_guide:
                        print(f"Van phong: {style_guide}")

        chapter_gen = crawl_chapters_stream(
            args.start_url, args.raw,
            max_chapters=chapter_limit,
            should_stop=lambda: _stop_flag
        )

        print("\n=== Buoc 2/4: Dich ngay theo tung chuong vua cao ===")
        failed = translate_novel_stream(
            chapter_gen, translated_file, args.glossary, api_key,
            model=args.model, temperature=args.temperature,
            thinking=not args.no_thinking,
            style_guide=style_guide,
            should_stop=lambda: _stop_flag
        )

    elif args.start_url:
        crawl_novel(args.start_url, args.raw, should_stop=lambda: _stop_flag)
    elif os.path.exists(args.raw):
        print(f"Bo qua cao - da co san {args.raw}.")
    else:
        print(f"Error: khong co --start-url va khong tim thay {args.raw}.")
        sys.exit(1)

    if not args.stream:
        print("\n=== Buoc 2/4: Dich bang DeepSeek API ===")
        failed = translate_novel(args.raw, translated_file, args.glossary, api_key, model=args.model,
                         temperature=args.temperature, workers=args.workers, thinking=not args.no_thinking,
                         style_detect=not args.no_style_detect, avoid_peak=not args.allow_peak,
                         should_stop=lambda: _stop_flag)

    print("\n=== Buoc 3/4: Kiem tra chat luong (Validation) ===")
    warnings = validate_translation(args.raw, translated_file)
    if warnings:
        print("\n[CANH BAO] Phat hien van de trong ban dich. Ban co the can kiem tra lai.")

    print("\n=== Buoc 4/4: Dong goi EPUB ===")
    epub_path = args.epub or f"{args.title}.epub"
    if failed:
        print(f"CANH BAO: Co {len(failed)} chuong dich that bai. EPUB se KHONG day du.")
        for fc in failed:
            print(f"  - Chuong {fc['index']}: {fc['title']}")
    build_epub(translated_file, epub_path, args.title, args.author)
    print(f"\nHoan tat! EPUB: {epub_path}")


if __name__ == "__main__":
    main()
