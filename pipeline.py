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
from crawler import DEFAULT_OUTPUT, crawl_novel
from deepseek_translate import load_dotenv, translate_novel
from output_storage import is_termux, save_output_file


VALID_FORMATS = ("epub", "pdf", "both")


def _parse_formats(raw: str) -> list[str]:
    if raw == "both":
        return ["epub", "pdf"]
    if raw in ("epub", "pdf"):
        return [raw]
    # Cho phep truyen "epub,pdf" (giu tuong thich neu ai script quen)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        if p not in ("epub", "pdf"):
            raise ValueError(f"Format khong ho tro: {p}. Chi cho: epub | pdf | both.")
    return parts or ["epub"]


def main():
    parser = argparse.ArgumentParser(description="Quy trinh: Cao -> Dich DeepSeek -> Dong goi EPUB")
    parser.add_argument("--start-url", default=None,
                         help="URL chuong 1 de cao (bo qua neu da co san --raw)")
    parser.add_argument("--raw", default=DEFAULT_OUTPUT, help="File luu noi dung tho da cao")
    parser.add_argument("--translated", default=None,
                         help="File luu ban dich, mac dinh <raw>.viet.txt")
    parser.add_argument("--title", required=True, help="Ten truyen (EPUB metadata + ten file EPUB)")
    parser.add_argument("--author", default="Unknown")
    parser.add_argument("--epub", default=None, help="Duong dan EPUB dau ra, mac dinh <title>.epub")
    parser.add_argument("--pdf", default=None, help="Duong dan PDF dau ra, mac dinh <title>.pdf")
    parser.add_argument("--formats", default="epub", choices=list(VALID_FORMATS),
                         help="Dinh dang xuat: epub (mac dinh) | pdf | both. "
                              "PDF chi la fallback cho Termux khi khong co reader EPUB.")
    parser.add_argument("--to-documents", dest="to_documents", action="store_true", default=None,
                         help="Sau khi tao xong, di chuyen san pham sang thu muc Documents "
                              "user-visible (~/storage/shared/Documents/DichTruyen tren Termux, "
                              "~/Documents/DichTruyen tren PC). Mac dinh: bat neu la Termux.")
    parser.add_argument("--no-to-documents", dest="to_documents", action="store_false",
                         help="Tat viec di chuyen tu dong sang Documents (giu file o thu muc hien tai).")
    parser.add_argument("--glossary", default="glossary.json")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--temperature", type=float, default=1.3)
    parser.add_argument("--workers", type=int, default=1,
                         help="So chuong dich song song (>1 danh doi tinh nhat quan ten rieng lay toc do)")
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

    print("=== Buoc 1/3: Cao truyen ===")
    if args.start_url:
        crawl_novel(args.start_url, args.raw, should_stop=lambda: _stop_flag)
    elif os.path.exists(args.raw):
        print(f"Bo qua cao - da co san {args.raw}.")
    else:
        print(f"Error: khong co --start-url va khong tim thay {args.raw}.")
        sys.exit(1)

    print("\n=== Buoc 2/3: Dich bang DeepSeek API ===")
    failed = translate_novel(args.raw, translated_file, args.glossary, api_key, model=args.model,
                     temperature=args.temperature, workers=args.workers, thinking=not args.no_thinking,
                     style_detect=not args.no_style_detect, avoid_peak=not args.allow_peak,
                     should_stop=lambda: _stop_flag)

    formats = _parse_formats(args.formats)
    print(f"\n=== Buoc 3/3: Dong goi {'/'.join(f.upper() for f in formats)} ===")
    if failed:
        print(f"CANH BAO: Co {len(failed)} chuong dich that bai. San pham dau ra se KHONG day du.")
        for fc in failed:
            print(f"  - Chuong {fc['index']}: {fc['title']}")

    outputs = []
    if "epub" in formats:
        epub_path = args.epub or f"{args.title}.epub"
        build_epub(translated_file, epub_path, args.title, args.author)
        print(f"EPUB: {epub_path}")
        outputs.append(epub_path)
    if "pdf" in formats:
        # Import muon: khong bat buoc fpdf2 phai co san neu user chi lay EPUB
        from build_pdf import build_pdf
        pdf_path = args.pdf or f"{args.title}.pdf"
        try:
            build_pdf(translated_file, pdf_path, args.title, args.author)
            print(f"PDF: {pdf_path}")
            outputs.append(pdf_path)
        except Exception as e:
            print(f"LOI xuat PDF: {e}")
            # Khong sys.exit - EPUB (neu co) van dung; user chi mat PDF fallback

    to_docs = args.to_documents if args.to_documents is not None else is_termux()
    if to_docs and outputs:
        print("\n=== Luu vao Documents user-visible ===")
        for path in outputs:
            final_path, warn = save_output_file(path)
            if warn:
                print(f"CANH BAO: {warn} -> giu tam o {final_path}")
            else:
                print(f"[LUU] {final_path}")
    print("\nHoan tat!")


if __name__ == "__main__":
    main()
