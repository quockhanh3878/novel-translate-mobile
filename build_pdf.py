"""Create a Unicode PDF book from a translated novel text file.

The input format and chapter parsing are shared with ``build_epub.py``.  A
system font is used so Vietnamese text remains searchable and readable on the
Windows, Android/Termux, and Linux environments supported by the project.
"""

from __future__ import annotations

import argparse
import os
import sys
from html import escape
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from build_epub import copy_to_downloads
from crawler import is_novel_title_entry, parse_chapters


FONT_CANDIDATES = (
    (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ),
    (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ),
    (
        "/system/fonts/NotoSerif-Regular.ttf",
        "/system/fonts/NotoSerif-Bold.ttf",
    ),
    (
        "/system/fonts/NotoSans-Regular.ttf",
        "/system/fonts/NotoSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
)

PDF_REGULAR_FONT = "NovelPDFRegular"
PDF_BOLD_FONT = "NovelPDFBold"


def _font_candidates() -> list[tuple[Path, Path]]:
    candidates = [(Path(regular), Path(bold)) for regular, bold in FONT_CANDIDATES]
    windows_dir = os.environ.get("WINDIR")
    if windows_dir:
        fonts_dir = Path(windows_dir) / "Fonts"
        candidates[:0] = [
            (fonts_dir / "arial.ttf", fonts_dir / "arialbd.ttf"),
            (fonts_dir / "segoeui.ttf", fonts_dir / "segoeuib.ttf"),
        ]

    for base in (Path(__file__).resolve().parent, Path(sys.executable).resolve().parent):
        candidates.append(
            (
                base / "fonts" / "NotoSerif-Regular.ttf",
                base / "fonts" / "NotoSerif-Bold.ttf",
            )
        )
    return candidates


def _register_fonts() -> tuple[str, str]:
    if PDF_REGULAR_FONT in pdfmetrics.getRegisteredFontNames():
        return PDF_REGULAR_FONT, PDF_BOLD_FONT

    for regular_path, bold_path in _font_candidates():
        if not regular_path.is_file():
            continue
        if not bold_path.is_file():
            bold_path = regular_path
        try:
            pdfmetrics.registerFont(TTFont(PDF_REGULAR_FONT, str(regular_path)))
            pdfmetrics.registerFont(TTFont(PDF_BOLD_FONT, str(bold_path)))
            return PDF_REGULAR_FONT, PDF_BOLD_FONT
        except (OSError, ValueError, AssertionError):
            continue

    raise RuntimeError(
        "Khong tim thay font Unicode de tao PDF. Can Arial/Segoe UI tren Windows, "
        "Noto Sans tren Android, hoac DejaVu Sans tren Linux."
    )


def _paragraph_text(text: str) -> str:
    return escape(text).replace("\n", "<br/>")


def _draw_page_number(canvas, document) -> None:
    if canvas.getPageNumber() <= 1:
        return
    canvas.saveState()
    canvas.setFont(PDF_REGULAR_FONT, 9)
    canvas.setFillColor(HexColor("#666666"))
    canvas.drawCentredString(A4[0] / 2, 0.42 * inch, str(canvas.getPageNumber() - 1))
    canvas.restoreState()


def build_pdf(input_file: str, output_file: str, title: str, author: str) -> str:
    chapters = parse_chapters(input_file)
    if not chapters:
        raise ValueError(f"Khong tim thay chuong nao trong {input_file}")
    if is_novel_title_entry(chapters, 0):
        chapters = chapters[1:]
    if not chapters:
        raise ValueError(f"Khong tim thay noi dung chuong nao trong {input_file}")

    regular_font, bold_font = _register_fonts()
    out_dir = os.path.dirname(os.path.abspath(output_file)) or "."
    os.makedirs(out_dir, exist_ok=True)

    styles = getSampleStyleSheet()
    cover_title = ParagraphStyle(
        "NovelCoverTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=25,
        leading=32,
        alignment=TA_CENTER,
        textColor=HexColor("#17324d"),
        spaceAfter=24,
    )
    cover_meta = ParagraphStyle(
        "NovelCoverMeta",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=12,
        leading=18,
        alignment=TA_CENTER,
        textColor=HexColor("#555555"),
    )
    chapter_style = ParagraphStyle(
        "NovelChapter",
        parent=styles["Heading1"],
        fontName=bold_font,
        fontSize=17,
        leading=23,
        alignment=TA_CENTER,
        textColor=HexColor("#17324d"),
        spaceAfter=20,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "NovelBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=11.5,
        leading=19,
        alignment=TA_JUSTIFY,
        firstLineIndent=18,
        spaceAfter=9,
    )

    story = [
        Spacer(1, 2.35 * inch),
        Paragraph(_paragraph_text(title), cover_title),
        Paragraph(_paragraph_text(f"Tac gia: {author}"), cover_meta),
        Spacer(1, 0.25 * inch),
        Paragraph(_paragraph_text(f"{len(chapters)} chuong"), cover_meta),
        Spacer(1, 2.35 * inch),
        Paragraph("Ban dich tieng Viet", cover_meta),
        PageBreak(),
    ]

    for index, chapter in enumerate(chapters):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(_paragraph_text(chapter["title"]), chapter_style))
        for paragraph in chapter["paragraphs"]:
            story.append(Paragraph(_paragraph_text(paragraph), body_style))

    document = SimpleDocTemplate(
        output_file,
        pagesize=A4,
        rightMargin=0.78 * inch,
        leftMargin=0.78 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.7 * inch,
        title=title,
        author=author,
        subject="Ban dich tieu thuyet tieng Viet",
    )
    document.build(story, onFirstPage=_draw_page_number, onLaterPages=_draw_page_number)
    try:
        copy_to_downloads(output_file)
    except Exception as exc:
        print(f"Loi clone file PDF sang thu muc Download: {exc}")
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Dong goi file truyen da dich thanh PDF tieng Viet")
    parser.add_argument("--input", required=True, help="Duong dan den file txt")
    parser.add_argument("--output", default=None, help="Mac dinh: <title>.pdf")
    parser.add_argument("--title", default=None, help="Ten truyen")
    parser.add_argument("--author", default="Unknown", help="Ten tac gia")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: khong tim thay file input {args.input}.")
        return
    if not args.title:
        from crawler import guess_title

        args.title = guess_title(args.input)

    output_file = args.output or f"{args.title}.pdf"
    path = build_pdf(args.input, output_file, args.title, args.author)
    print(f"Da dong goi PDF tai: {path}")


if __name__ == "__main__":
    main()
