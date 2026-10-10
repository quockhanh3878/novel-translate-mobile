"""
test_deepseek_pipeline.py - Kiem tra parse_chapters/resume logic dung chung giua
deepseek_translate.py va build_epub.py, khong goi API that.

Chay: .venv\\Scripts\\python test_deepseek_pipeline.py
"""

import os
import tempfile
from datetime import datetime, timezone

import crawler
from deepseek_translate import (
    parse_chapters, count_translated_chapters, build_user_prompt,
    is_peak_hour, _peak_window_end, BEIJING_TZ,
)
from build_epub import parse_chapters as parse_chapters_epub, build_epub
from build_pdf import build_pdf


SAMPLE_ZH = """=== 第1章 开始 ===

你好世界。

第二段。

========================================

=== 第2章 继续 ===

再见。

========================================

"""

SAMPLE_VI = """=== Chương 1: Bắt đầu ===

Xin chào thế giới.

Đoạn hai.

========================================

"""


def demo():
    with tempfile.TemporaryDirectory() as d:
        zh_path = os.path.join(d, "zh.txt")
        with open(zh_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_ZH)

        chapters = parse_chapters(zh_path)
        assert len(chapters) == 2, chapters
        assert chapters[0]["title"] == "第1章 开始"
        assert chapters[0]["paragraphs"] == ["你好世界。", "第二段。"]
        assert chapters[1]["title"] == "第2章 继续"

        prompt = build_user_prompt(chapters[0])
        assert "你好世界" in prompt
        assert "你好 = Xin chao" not in prompt

        vi_path = os.path.join(d, "vi.txt")
        with open(vi_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_VI)
        assert count_translated_chapters(vi_path) == 1
        assert count_translated_chapters(os.path.join(d, "missing.txt")) == 0

        ch_epub = parse_chapters_epub(vi_path)
        assert len(ch_epub) == 1
        assert ch_epub[0]["title"] == "Chương 1: Bắt đầu"

        epub_out = os.path.join(d, "out.epub")
        result_path = build_epub(vi_path, epub_out, "Test Truyện", "Test Author")
        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0

        pdf_out = os.path.join(d, "out.pdf")
        pdf_result = build_pdf(vi_path, pdf_out, "Truyện kiểm thử", "Tác giả")
        assert os.path.exists(pdf_result)
        assert os.path.getsize(pdf_result) > 1000
        with open(pdf_result, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
        assert pdf_bytes.startswith(b"%PDF-")
        assert b"/FontFile" in pdf_bytes
        assert b"/ToUnicode" in pdf_bytes

        # crawl_novel phai TU DONG resume tu chuong ke tiep dua tren so chuong da co
        # trong file, khong dua vao so chuong ghi trong start_url - tranh cao trung
        # lap neu chay lai voi cung 1 URL chuong 1. Mock crawl_chapter de khong goi
        # mang that, chi kiem tra URL nao thuc su duoc fetch.
        raw_path = os.path.join(d, "raw.txt")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_ZH)  # da co san 2 chuong

        fetched_urls = []
        orig_crawl_chapter = crawler.crawl_chapter

        def fake_crawl_chapter(url, log=print):
            fetched_urls.append(url)
            return None  # gia lap 404 -> dung cao ngay

        crawler.crawl_chapter = fake_crawl_chapter
        try:
            crawler.crawl_novel("https://example.com/novel_1.html", raw_path, log=lambda m: None)
        finally:
            crawler.crawl_chapter = orig_crawl_chapter

        assert fetched_urls == ["https://example.com/novel_3.html"], fetched_urls

    # Gio cao diem DeepSeek: 9-12h va 14-18h gio Bac Kinh. Dung datetime co dinh
    # (khong dung datetime.now() that) de test khong bi flaky/treo theo dong ho may.
    # 2026-01-06 la thu 3 binh thuong (2026-01-01 la ngay le nen khong con la cao diem).
    assert is_peak_hour(datetime(2026, 1, 6, 9, 0, tzinfo=BEIJING_TZ)) is True  # dau khung
    assert is_peak_hour(datetime(2026, 1, 6, 11, 59, tzinfo=BEIJING_TZ)) is True
    assert is_peak_hour(datetime(2026, 1, 6, 12, 0, tzinfo=BEIJING_TZ)) is False  # het khung (exclusive)
    assert is_peak_hour(datetime(2026, 1, 6, 13, 30, tzinfo=BEIJING_TZ)) is False  # nghi trua
    assert is_peak_hour(datetime(2026, 1, 6, 14, 0, tzinfo=BEIJING_TZ)) is True
    assert is_peak_hour(datetime(2026, 1, 6, 18, 0, tzinfo=BEIJING_TZ)) is False
    assert is_peak_hour(datetime(2026, 1, 6, 22, 0, tzinfo=BEIJING_TZ)) is False  # ngoai gio
    # Chi thu 2-6: 2026-01-03 la thu 7, 2026-01-04 chu nhat, 2026-01-05 thu 2.
    assert is_peak_hour(datetime(2026, 1, 3, 10, 0, tzinfo=BEIJING_TZ)) is False
    assert is_peak_hour(datetime(2026, 1, 4, 15, 0, tzinfo=BEIJING_TZ)) is False
    assert is_peak_hour(datetime(2026, 1, 5, 10, 0, tzinfo=BEIJING_TZ)) is True
    # Gio UTC: 01:30 UTC thu 2 = 09:30 Bac Kinh thu 2 -> cao diem.
    assert is_peak_hour(datetime(2026, 1, 5, 1, 30, tzinfo=timezone.utc)) is True

    end = _peak_window_end(datetime(2026, 1, 1, 10, 30, tzinfo=BEIJING_TZ))
    assert (end.hour, end.minute) == (12, 0), end
    end2 = _peak_window_end(datetime(2026, 1, 1, 15, 0, tzinfo=BEIJING_TZ))
    assert (end2.hour, end2.minute) == (18, 0), end2

    # Test detect_style_guide tra ve dict
    from deepseek_translate import detect_style_guide
    import deepseek_translate
    
    orig_call_deepseek = deepseek_translate.call_deepseek
    def fake_call_deepseek(*args, **kwargs):
        return {
            "style_guide": "Tien hiep, van phong trang trong.",
            "term_categories": "cong phap, tong mon, phap bao"
        }
    
    deepseek_translate.call_deepseek = fake_call_deepseek
    try:
        style_data = detect_style_guide([{"title": "1", "paragraphs": ["a"]}], "fake_api_key", "fake_model")
        assert isinstance(style_data, dict)
        assert style_data["style_guide"] == "Tien hiep, van phong trang trong."
        assert style_data["term_categories"] == "cong phap, tong mon, phap bao"
    finally:
        deepseek_translate.call_deepseek = orig_call_deepseek

    print("OK: parse/resume/epub-build hoat dong dung nhu ky vong.")


if __name__ == "__main__":
    demo()
