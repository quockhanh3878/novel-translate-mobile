"""
test_deepseek_pipeline.py - Kiem tra parse_chapters/resume logic dung chung giua
deepseek_translate.py va build_epub.py, khong goi API that.

Chay: .venv\\Scripts\\python test_deepseek_pipeline.py
"""

import os
import tempfile
from datetime import datetime

import crawler
from deepseek_translate import (
    parse_chapters, count_translated_chapters, build_user_prompt,
    is_peak_hour, _peak_window_end, BEIJING_TZ,
)
from build_epub import parse_chapters as parse_chapters_epub, build_epub


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

        prompt = build_user_prompt(chapters[0], {"你好": "Xin chao"})
        assert "你好 = Xin chao" in prompt
        assert "你好世界" in prompt

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
    assert is_peak_hour(datetime(2026, 1, 1, 9, 0, tzinfo=BEIJING_TZ)) is True  # dau khung
    assert is_peak_hour(datetime(2026, 1, 1, 11, 59, tzinfo=BEIJING_TZ)) is True
    assert is_peak_hour(datetime(2026, 1, 1, 12, 0, tzinfo=BEIJING_TZ)) is False  # het khung (exclusive)
    assert is_peak_hour(datetime(2026, 1, 1, 13, 30, tzinfo=BEIJING_TZ)) is False  # nghi trua
    assert is_peak_hour(datetime(2026, 1, 1, 14, 0, tzinfo=BEIJING_TZ)) is True
    assert is_peak_hour(datetime(2026, 1, 1, 18, 0, tzinfo=BEIJING_TZ)) is False
    assert is_peak_hour(datetime(2026, 1, 1, 22, 0, tzinfo=BEIJING_TZ)) is False  # ngoai gio

    end = _peak_window_end(datetime(2026, 1, 1, 10, 30, tzinfo=BEIJING_TZ))
    assert (end.hour, end.minute) == (12, 0), end
    end2 = _peak_window_end(datetime(2026, 1, 1, 15, 0, tzinfo=BEIJING_TZ))
    assert (end2.hour, end2.minute) == (18, 0), end2

    print("OK: parse/resume/epub-build hoat dong dung nhu ky vong.")


if __name__ == "__main__":
    demo()
