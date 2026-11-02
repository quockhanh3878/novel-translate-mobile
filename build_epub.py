"""
build_epub.py - Dong goi file truyen da dich (dinh dang === Chuong ===, cung
dinh dang voi crawler.py/deepseek_translate.py/translate_novel.py) thanh EPUB
toi uu cho doc tieng Viet (font/spacing/TOC).

Tach rieng khoi novel_gui.py vi novel_gui.py import app.py -> nap model MarianMT
(ONNX) ngay khi import, khong can thiet cho buoc dong goi EPUB don thuan.

Su dung:
    # PC (Windows):
    .venv\\Scripts\\python build_epub.py --input truyen_viet.txt --title "Ten Truyen" --author "Tac gia"
    # Mobile (Termux) / Linux / macOS:
    .venv/bin/python build_epub.py --input truyen_viet.txt --title "Ten Truyen" --author "Tac gia"
"""

from __future__ import annotations

import argparse
import os
import time
import zipfile
from html import escape

from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

from crawler import is_novel_title_entry, parse_chapters

EPUB_CSS = """
body {
    font-family: "Noto Serif", "Georgia", serif;
    font-size: 1.15em;
    line-height: 1.8;
    margin: 1.5em 1.0em;
    background-color: #ffffff;
    color: #111111;
}
h1, h2 {
    text-align: center;
    font-size: 1.5em;
    margin-bottom: 1.2em;
    color: #007acc;
}
p {
    text-indent: 1.5em;
    margin: 0.6em 0;
    text-align: justify;
}
"""


def generate_cover_image(title: str, author: str, output_path: str) -> None:
    width, height = 600, 800
    image = Image.new("RGB", (width, height), "#1a1a1a")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, width - 20, height - 20], outline="#007acc", width=3)
    font = ImageFont.load_default()
    draw.text((width // 2, height // 3), title, fill="#ffffff", font=font, anchor="mm")
    draw.text((width // 2, height // 2), f"Tac gia: {author}", fill="#cccccc", font=font, anchor="mm")
    draw.text((width // 2, height - 100), "Dich boi DeepSeek API", fill="#888888", font=font, anchor="mm")
    image.save(output_path, "JPEG")


def copy_to_downloads(src_path: str) -> str | None:
    """
    Sao chep file dau ra sang thu muc Download cua thiet bi (Android, Windows, macOS, Linux).
    """
    import os
    import shutil

    if not os.path.exists(src_path):
        return None

    filename = os.path.basename(src_path)

    # Kiem tra thu muc Download tren Android (Termux)
    android_download = os.path.expanduser("~/storage/shared/Download")
    is_termux = os.path.exists("/data/data/com.termux")
    shared_root = os.path.expanduser("~/storage/shared")
    if is_termux and (not os.path.islink(shared_root) or not os.path.isdir(shared_root)):
        print("Khong copy EPUB ra bo nho chung: Termux chua duoc cap quyen storage.")
        return None
    if os.path.isdir(android_download):
        dest_dir = android_download
    elif os.path.isdir("/sdcard/Download"):
        dest_dir = "/sdcard/Download"
    else:
        # Kiem tra tren cac he dieu hanh khac (Windows, macOS, Linux)
        dest_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    if not os.path.exists(dest_dir):
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception:
            pass

    if os.path.isdir(dest_dir):
        dest_path = os.path.join(dest_dir, filename)
        try:
            shutil.copy2(src_path, dest_path)
            return dest_path
        except Exception as e:
            print(f"Loi khi clone file sang thu muc Download: {e}")
            return None
    return None


def build_epub(input_file: str, output_file: str, title: str, author: str) -> str:
    chapters = parse_chapters(input_file)
    if not chapters:
        raise ValueError(f"Khong tim thay chuong nao trong {input_file}")
    if is_novel_title_entry(chapters, 0):
        chapters = chapters[1:]

    book = epub.EpubBook()
    book.set_identifier(f"novel-translation-{int(time.time())}")
    book.set_title(title)
    book.set_language("vi")
    book.add_author(author)

    out_dir = os.path.dirname(os.path.abspath(output_file)) or "."
    os.makedirs(out_dir, exist_ok=True)
    cover_path = os.path.join(out_dir, "_cover_tmp.jpg")
    generate_cover_image(title, author, cover_path)
    with open(cover_path, "rb") as f:
        book.set_cover("cover.jpg", f.read())
    os.remove(cover_path)

    style_item = epub.EpubItem(
        uid="style_pub", file_name="style/epub.css", media_type="text/css", content=EPUB_CSS
    )
    book.add_item(style_item)

    epub_chapters = []
    for idx, ch in enumerate(chapters, 1):
        title_esc = escape(ch["title"])
        paragraphs_html = "".join(f"<p>{escape(p)}</p>" for p in ch["paragraphs"])
        content_html = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{title_esc}</title>
    <link rel="stylesheet" href="style/epub.css" type="text/css"/>
</head>
<body>
    <h1>{title_esc}</h1>
    {paragraphs_html}
</body>
</html>
"""
        epub_ch = epub.EpubHtml(title=ch["title"], file_name=f"chap_{idx:03d}.xhtml", lang="vi")
        epub_ch.content = content_html
        epub_ch.add_item(style_item)
        book.add_item(epub_ch)
        epub_chapters.append(epub_ch)

    book.toc = tuple(epub.Link(c.file_name, c.title, c.file_name) for c in epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + epub_chapters

    epub.write_epub(output_file, book, {})
    _record_packaged_source(input_file, output_file)
    try:
        copy_to_downloads(output_file)
    except Exception as e:
        print(f"Loi clone file sang Download: {e}")
    return output_file


_LAST_PACKAGED_SOURCE: dict[str, tuple[str, int, int]] = {}


def _record_packaged_source(translated_file: str, package_path: str) -> None:
    """Ghi nhan trang thai file dich vua duoc dong goi vao package_path."""
    try:
        if not os.path.isfile(translated_file) or not os.path.isfile(package_path):
            return
        trans_stat = os.stat(translated_file)
        pkg_stat = os.stat(package_path)
        if pkg_stat.st_mtime_ns < trans_stat.st_mtime_ns:
            os.utime(package_path, ns=(trans_stat.st_atime_ns, trans_stat.st_mtime_ns))
        _LAST_PACKAGED_SOURCE[os.path.abspath(package_path)] = (
            os.path.abspath(translated_file),
            trans_stat.st_size,
            trans_stat.st_mtime_ns,
        )
    except OSError:
        pass


def is_package_up_to_date(translated_file: str, package_path: str) -> bool:
    """Kiem tra file dong goi (EPUB/PDF) da ton tai va cap nhat day du theo translated_file chua."""
    try:
        if not translated_file or not package_path:
            return False
        if not os.path.isfile(translated_file) or not os.path.isfile(package_path):
            return False
        trans_stat = os.stat(translated_file)
        pkg_stat = os.stat(package_path)
        if trans_stat.st_size <= 0 or pkg_stat.st_size <= 0:
            return False
        if pkg_stat.st_mtime_ns < trans_stat.st_mtime_ns:
            return False

        abs_trans = os.path.abspath(translated_file)
        abs_pkg = os.path.abspath(package_path)
        recorded = _LAST_PACKAGED_SOURCE.get(abs_pkg)
        if recorded is not None and recorded != (abs_trans, trans_stat.st_size, trans_stat.st_mtime_ns):
            return False

        lower_pkg = package_path.lower()
        if lower_pkg.endswith(".epub"):
            if zipfile.is_zipfile(package_path):
                chapters = parse_chapters(translated_file)
                if is_novel_title_entry(chapters, 0):
                    chapters = chapters[1:]
                if not chapters:
                    return False
                with zipfile.ZipFile(package_path, "r") as zf:
                    epub_chap_count = sum(
                        1
                        for name in zf.namelist()
                        if os.path.basename(name).startswith("chap_") and name.endswith(".xhtml")
                    )
                return epub_chap_count == len(chapters)
            return recorded is not None

        if lower_pkg.endswith(".pdf"):
            with open(package_path, "rb") as f:
                header = f.read(5)
            if header == b"%PDF-":
                return True
            return recorded is not None

        return True
    except OSError:
        return False


def ensure_packaged(
    translated_file: str,
    epub_path: str,
    pdf_path: str,
    title: str,
    author: str = "Unknown",
    build_epub_fn=None,
    build_pdf_fn=None,
) -> dict[str, bool]:
    """Chi dong goi EPUB/PDF khi file chua ton tai hoac da cu so voi translated_file."""
    if build_epub_fn is None:
        build_epub_fn = build_epub
    if build_pdf_fn is None:
        from build_pdf import build_pdf as _default_build_pdf
        build_pdf_fn = _default_build_pdf

    epub_built = False
    pdf_built = False

    if epub_path and not is_package_up_to_date(translated_file, epub_path):
        build_epub_fn(translated_file, epub_path, title, author)
        _record_packaged_source(translated_file, epub_path)
        epub_built = True

    if pdf_path and not is_package_up_to_date(translated_file, pdf_path):
        build_pdf_fn(translated_file, pdf_path, title, author)
        _record_packaged_source(translated_file, pdf_path)
        pdf_built = True

    return {"epub_built": epub_built, "pdf_built": pdf_built}


def main():
    parser = argparse.ArgumentParser(description="Dong goi file truyen da dich thanh EPUB tieng Viet")
    parser.add_argument("--input", required=True, help="Duong dan den file txt (vi du: truyen_viet.txt)")
    parser.add_argument("--output", default=None, help="Mac dinh: <title>.epub")
    parser.add_argument("--title", default=None, help="Ten truyen (neu khong nhap se tu doan tu ten file)")
    parser.add_argument("--author", default="Unknown", help="Ten tac gia")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: khong tim thay file input {args.input}.")
        return

    # Tu doan ten truyen tu ten file neu khong duoc cung cap
    if not args.title:
        from crawler import guess_title
        args.title = guess_title(args.input)

    output_file = args.output or f"{args.title}.epub"
    path = build_epub(args.input, output_file, args.title, args.author)
    print(f"Da dong goi EPUB tai: {path}")


if __name__ == "__main__":
    main()
