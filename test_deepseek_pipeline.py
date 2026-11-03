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
from build_epub import parse_chapters as parse_chapters_epub, build_epub, ensure_packaged, is_package_up_to_date
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
        from novel_metadata import prepare_profile
        from deepseek_translate import DEFAULT_MODEL
        prepare_profile(zh_path, vi_path, model=DEFAULT_MODEL)

        ch_epub = parse_chapters_epub(vi_path)
        assert len(ch_epub) == 1
        assert ch_epub[0]["title"] == "Chương 1: Bắt đầu"

        epub_out = os.path.join(d, "out.epub")
        result_path = build_epub(vi_path, epub_out, "Test Truyện", "Test Author")
        assert os.path.exists(result_path)
        assert os.path.getsize(result_path) > 0

        pdf_out = os.path.join(d, "out.pdf")
        pdf_result = build_pdf(vi_path, pdf_out, "Test Truyện", "Test Author")
        assert os.path.exists(pdf_result)
        assert os.path.getsize(pdf_result) > 1000
        with open(pdf_result, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
        assert pdf_bytes.startswith(b"%PDF-")
        assert b"/FontFile" in pdf_bytes
        assert b"/ToUnicode" in pdf_bytes

        # Kiem tra chong dong goi trung khi da co san file EPUB/PDF cap nhat:
        assert is_package_up_to_date(vi_path, epub_out) is True
        assert is_package_up_to_date(vi_path, pdf_out) is True

        epub_calls = []
        pdf_calls = []

        def tracked_epub(inp, out, title, author):
            epub_calls.append(out)
            return build_epub(inp, out, title, author)

        def tracked_pdf(inp, out, title, author):
            pdf_calls.append(out)
            return build_pdf(inp, out, title, author)

        # Khi ca EPUB va PDF deu da cap nhat, ensure_packaged phai bo qua ca hai
        res_skip = ensure_packaged(
            vi_path, epub_out, pdf_out, "Test Truyện", "Test Author",
            build_epub_fn=tracked_epub, build_pdf_fn=tracked_pdf,
        )
        assert res_skip == {"epub_built": False, "pdf_built": False}, res_skip
        assert epub_calls == [] and pdf_calls == [], (epub_calls, pdf_calls)

        # Neu xoa rieng file PDF, chi dong goi lai PDF, giu nguyen EPUB
        os.remove(pdf_out)
        res_partial = ensure_packaged(
            vi_path, epub_out, pdf_out, "Test Truyện", "Test Author",
            build_epub_fn=tracked_epub, build_pdf_fn=tracked_pdf,
        )
        assert res_partial == {"epub_built": False, "pdf_built": True}, res_partial
        assert epub_calls == [] and len(pdf_calls) == 1, (epub_calls, pdf_calls)

        # Khi file dich co them chuong moi, ca EPUB va PDF phai duoc dong goi cap nhat
        with open(vi_path, "a", encoding="utf-8") as f:
            f.write("=== Chương 2: Tiếp theo ===\n\nTạm biệt.\n\n" + "=" * 40 + "\n\n")
        assert is_package_up_to_date(vi_path, epub_out) is False
        assert is_package_up_to_date(vi_path, pdf_out) is False
        res_rebuild = ensure_packaged(
            vi_path, epub_out, pdf_out, "Test Truyện", "Test Author",
            build_epub_fn=tracked_epub, build_pdf_fn=tracked_pdf,
        )
        assert res_rebuild == {"epub_built": True, "pdf_built": True}, res_rebuild
        assert len(epub_calls) == 1 and len(pdf_calls) == 2, (epub_calls, pdf_calls)

        # Goi lai ensure_packaged ngay sau do (nhu Buoc 4/4 sau on_chapter) phai bo qua
        res_after = ensure_packaged(
            vi_path, epub_out, pdf_out, "Test Truyện", "Test Author",
            build_epub_fn=tracked_epub, build_pdf_fn=tracked_pdf,
        )
        assert res_after == {"epub_built": False, "pdf_built": False}, res_after
        assert len(epub_calls) == 1 and len(pdf_calls) == 2, (epub_calls, pdf_calls)

        # Kiem tra pipeline.main(): khi file dich da du 2 chuong va EPUB/PDF da co san,
        # chay lai pipeline khong duoc dong goi trung (0 lan goi build_epub / build_pdf).
        import pipeline
        import sys
        orig_argv = sys.argv
        orig_pipe_epub = pipeline.build_epub
        orig_pipe_pdf = pipeline.build_pdf
        pipe_epub_calls = []
        pipe_pdf_calls = []
        pipeline.build_epub = lambda *a, **kw: pipe_epub_calls.append(a)
        pipeline.build_pdf = lambda *a, **kw: pipe_pdf_calls.append(a)
        try:
            sys.argv = [
                "pipeline.py",
                "--raw", zh_path,
                "--translated", vi_path,
                "--epub", epub_out,
                "--pdf", pdf_out,
                "--title", "Test Truyện",
                "--author", "Test Author",
                "--api-key", "fake-key",
                "--no-style-detect",
                "--no-prepare",
                "--allow-peak",
            ]
            pipeline.main()
        finally:
            sys.argv = orig_argv
            pipeline.build_epub = orig_pipe_epub
            pipeline.build_pdf = orig_pipe_pdf
        assert pipe_epub_calls == [] and pipe_pdf_calls == [], (pipe_epub_calls, pipe_pdf_calls)

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
            return None  # gia lap 404 -> thu them vai trang roi dung

        crawler.crawl_chapter = fake_crawl_chapter
        try:
            crawler.crawl_novel("https://example.com/novel_1.html", raw_path, log=lambda m: None)
        finally:
            crawler.crawl_chapter = orig_crawl_chapter

        expected = [f"https://example.com/novel_{n}.html" for n in range(3, 4 + crawler.MAX_MISSING_INDEXES)]
        assert fetched_urls == expected, fetched_urls

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
