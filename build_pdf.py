"""build_pdf.py - Xuat truyen da dich sang PDF (fallback cho EPUB).

Danh cho thiet bi Termux/Android khong co reader EPUB (Google Files, Drive, PDF
Viewer, WPS... deu mo PDF san). Su dung fpdf2 - pure Python, khong can compile,
cai duoc ngay tren Termux ma khong keo thu vien nang.

Van de font tieng Viet: fpdf2 default (Helvetica) la Type1 Latin-1, KHONG render
duoc dau tieng Viet. Bat buoc phai add_font 1 file TTF ho tro Unicode. Module
nay tu do quet cac path font quen thuoc tren Android/Termux/Linux/macOS/Windows
va chon file dau tien tim thay.
"""
from __future__ import annotations

import argparse
import os
from typing import Optional

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from crawler import parse_chapters

# fpdf2 2.8+ mac dinh giu con tro o goc phai duoi cell (khong xuong dong tra ve
# le trai) - gay loi "Not enough horizontal space" o multi_cell ke tiep. Truyen
# NEXT_LINE_KW vao moi multi_cell/cell de xuong dong ve le trai giong hanh vi
# fpdf1 (cung la hanh vi ma layout truyen mong doi).
NEXT_LINE_KW = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

# Cac font TTF/OTF co tieng Viet day du (dau thanh) tren tung he dieu hanh.
# Uu tien font khong bien (non-variable) vi fpdf2 chua ho tro variable font tot.
FONT_REGULAR_CANDIDATES = [
    # Android (system fonts world-readable, khong can quyen)
    "/system/fonts/Roboto-Regular.ttf",
    "/system/fonts/RobotoStatic-Regular.ttf",
    "/system/fonts/NotoSerif-Regular.ttf",
    "/system/fonts/DroidSans.ttf",
    # Termux (sau `pkg install fontconfig` hoac tuong tu)
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/data/data/com.termux/files/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/data/data/com.termux/files/usr/share/fonts/noto/NotoSans-Regular.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    # macOS
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
]

FONT_BOLD_CANDIDATES = [
    "/system/fonts/Roboto-Bold.ttf",
    "/system/fonts/RobotoStatic-Bold.ttf",
    "/system/fonts/NotoSerif-Bold.ttf",
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/data/data/com.termux/files/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/data/data/com.termux/files/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/seguibl.ttf",
    "C:/Windows/Fonts/tahomabd.ttf",
]


def _find_font(candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


class _NovelPDF(FPDF):
    """FPDF con voi footer so trang (bo qua trang bia + muc luc)."""

    body_font = "Book"

    def footer(self):  # noqa: D401 - fpdf2 override
        if self.page_no() <= 2:
            return
        self.set_y(-12)
        self.set_font(self.body_font, size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, str(self.page_no() - 2), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def build_pdf(input_file: str, output_file: str, title: str, author: str) -> str:
    """Doc file da dich (dinh dang === Chuong === chung voi build_epub.py) va xuat PDF."""
    chapters = parse_chapters(input_file)
    if not chapters:
        raise ValueError(f"Khong tim thay chuong nao trong {input_file}")

    font_regular = _find_font(FONT_REGULAR_CANDIDATES)
    if not font_regular:
        raise RuntimeError(
            "Khong tim thay font TTF ho tro tieng Viet nao tren he thong. "
            "Termux: `pkg install fontconfig` (co san DejaVuSans). "
            "Debian/Ubuntu: `apt install fonts-dejavu`. "
            "Windows/macOS: kiem tra Arial hoac Segoe/Helvetica co san."
        )
    font_bold = _find_font(FONT_BOLD_CANDIDATES) or font_regular

    pdf = _NovelPDF(format="A5", unit="mm")
    pdf.set_title(title)
    pdf.set_author(author)
    pdf.set_creator("DeepSeek Novel Translator")
    pdf.set_margins(left=12, top=15, right=12)
    pdf.set_auto_page_break(auto=True, margin=15)
    # fpdf2 2.7+: khong can uni=True (unicode la mac dinh voi add_font TTF)
    pdf.add_font(_NovelPDF.body_font, "", font_regular)
    pdf.add_font(_NovelPDF.body_font, "B", font_bold)

    # --- Trang bia ---
    pdf.add_page()
    pdf.set_font(_NovelPDF.body_font, "B", 22)
    pdf.set_text_color(0, 122, 204)
    pdf.ln(40)
    pdf.multi_cell(0, 12, title, align="C", **NEXT_LINE_KW)
    pdf.ln(8)
    pdf.set_font(_NovelPDF.body_font, "", 14)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 8, f"Tac gia: {author}", align="C", **NEXT_LINE_KW)
    pdf.ln(80)
    pdf.set_font(_NovelPDF.body_font, "", 10)
    pdf.set_text_color(140, 140, 140)
    pdf.multi_cell(0, 6, "Dich bang DeepSeek API", align="C", **NEXT_LINE_KW)

    # --- Muc luc ---
    pdf.add_page()
    pdf.set_font(_NovelPDF.body_font, "B", 16)
    pdf.set_text_color(0, 122, 204)
    pdf.multi_cell(0, 12, "Muc luc", align="C", **NEXT_LINE_KW)
    pdf.ln(4)
    pdf.set_font(_NovelPDF.body_font, "", 11)
    pdf.set_text_color(30, 30, 30)
    for idx, ch in enumerate(chapters, 1):
        pdf.multi_cell(0, 6, f"{idx:>3}. {ch['title']}", **NEXT_LINE_KW)

    # --- Chuong ---
    for ch in chapters:
        pdf.add_page()
        pdf.set_font(_NovelPDF.body_font, "B", 15)
        pdf.set_text_color(0, 122, 204)
        pdf.multi_cell(0, 10, ch["title"], align="C", **NEXT_LINE_KW)
        pdf.ln(4)
        pdf.set_font(_NovelPDF.body_font, "", 12)
        pdf.set_text_color(20, 20, 20)
        for p in ch["paragraphs"]:
            # Thut le dau doan bang 4 khoang trang - PDF khong ho tro text-indent CSS
            pdf.multi_cell(0, 7, "    " + p, align="J", **NEXT_LINE_KW)
            pdf.ln(1)

    pdf.output(output_file)
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Xuat truyen da dich sang PDF tieng Viet")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None, help="Mac dinh: <title>.pdf")
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="Unknown")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: khong tim thay file input {args.input}.")
        return

    output_file = args.output or f"{args.title}.pdf"
    path = build_pdf(args.input, output_file, args.title, args.author)
    print(f"Da dong goi PDF tai: {path}")


if __name__ == "__main__":
    main()
