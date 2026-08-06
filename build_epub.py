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
from html import escape

from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

from crawler import parse_chapters

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


def build_epub(input_file: str, output_file: str, title: str, author: str) -> str:
    chapters = parse_chapters(input_file)
    if not chapters:
        raise ValueError(f"Khong tim thay chuong nao trong {input_file}")

    book = epub.EpubBook()
    book.set_identifier(f"novel-translation-{int(time.time())}")
    book.set_title(title)
    book.set_language("vi")
    book.add_author(author)

    out_dir = os.path.dirname(os.path.abspath(output_file)) or "."
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
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Dong goi file truyen da dich thanh EPUB tieng Viet")
    parser.add_argument("--input", default="truyen_de_tam_trung_nhan_cach_viet_deepseek.txt")
    parser.add_argument("--output", default=None, help="Mac dinh: <title>.epub")
    parser.add_argument("--title", default="Đệ Tam Trùng Nhân Cách")
    parser.add_argument("--author", default="Thường Thư Hân")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: khong tim thay file input {args.input}.")
        return

    output_file = args.output or f"{args.title}.epub"
    path = build_epub(args.input, output_file, args.title, args.author)
    print(f"Da dong goi EPUB tai: {path}")


if __name__ == "__main__":
    main()
