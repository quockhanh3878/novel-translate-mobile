"""Kiem tra danh so chuong theo so goc va bo qua/dich lai chuong o che do stream + thuong.

Chay: python test_stream_mode.py
"""

import os
import tempfile

import deepseek_translate as dt
from crawler import CHAPTER_SEP, iter_chapters_from_file, parse_chapters


def write_chapter(handle, title, text):
    handle.write(f"=== {title} ===\n\n{text}\n\n{CHAPTER_SEP}")


def fake_translate(calls):
    def _fake(chapter, *args, chapter_idx=None, **kwargs):
        calls.append((chapter_idx, chapter["title"]))
        title = "Hôm nay ra muộn" if "晚更" in chapter["title"] else "Tên"
        return {"title": title, "paragraphs": [f"Viet {chapter['title']}"], "new_terms": {},
                "idioms": {}, "term_warnings": [], "usage": {}}
    return _fake


def test_source_numbers():
    cases = {"第137 章　有因無果": 137, "1、歸零": 1, "第01章：大變活人": 1, "第一百零五章": 105,
             "第十章": 10, "第二十三章 x": 23, "Chapter 7: x": 7, "第１２章": 12, "第三回": 3,
             "第二卷總結": None, "今天晚更，10點前": None, "楔子": None}
    for title, want in cases.items():
        assert dt.source_chapter_number(title) == want, (title, dt.source_chapter_number(title))
    # Truyen khong danh so: van danh theo thu tu nhu truoc
    assert dt.chapter_labels(["Mở đầu", "Gặp gỡ", "第3章"]) == [1, 2, 3]
    print("PASS so chuong goc doc dung (so A-rap, so Han, '1、', Chapter) va truyen khong danh so")


def test_batch_labels_follow_source():
    """Muc thong bao khong chiem so; thieu chuong 4 thi chuong 5 van la 'Chương 5'."""
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        out = os.path.join(d, "raw.txt.viet.txt")
        with open(raw, "w", encoding="utf-8") as f:
            f.write("=== TRUYỆN ===\n\n")
            for t in ["第1章 一", "第2章 二", "今天晚更，10點前", "第3章 三", "第5章 五", "第一百零五章 六"]:
                write_chapter(f, t, "原文")
        calls = []
        original = dt.translate_chapter
        dt.translate_chapter = fake_translate(calls)
        try:
            dt.translate_novel(raw, out, None, "k", style_detect=False, prepare=False,
                               avoid_peak=False, log=lambda *_: None)
        finally:
            dt.translate_chapter = original
        titles = [c["title"] for c in parse_chapters(out)]
        assert titles == ["TRUYỆN", "Chương 1: Tên", "Chương 2: Tên", "Hôm nay ra muộn",
                          "Chương 3: Tên", "Chương 5: Tên", "Chương 105: Tên"], titles
    print("PASS che do thuong: tieu de theo so chuong goc, thong bao khong lam lech so")


def test_stream_skips_done_and_continues():
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        with open(raw, "w", encoding="utf-8") as f:
            f.write("=== TRUYỆN ===\n\n")
            for t in ["第1章", "第2章", "第3章", "今天晚更，10點前"] + [f"第{i}章" for i in range(4, 10)]:
                write_chapter(f, t, f"Goc {t}")
        out = os.path.join(d, "raw.txt.viet.txt")
        with open(out, "w", encoding="utf-8") as f:
            write_chapter(f, "TRUYỆN", "")
            write_chapter(f, "Chương 1", "Da dich 1")
            write_chapter(f, "Chương 2", "Da dich 2")

        calls = []
        original = dt.translate_chapter
        dt.translate_chapter = fake_translate(calls)
        try:
            dt.translate_novel_stream(iter_chapters_from_file(raw), out, None, "k",
                                      avoid_peak=False, max_chapters=3, log=lambda *_: None)
        finally:
            dt.translate_chapter = original

        assert [i for i, _ in calls] == [3, None, 4], calls
        assert [c["title"] for c in parse_chapters(out)] == [
            "TRUYỆN", "Chương 1", "Chương 2", "Chương 3: Tên", "Hôm nay ra muộn", "Chương 4: Tên"]
    print("PASS stream: bo qua chuong da dich, dich them du so chuong, thong bao khong chiem so")


def test_stream_quality_failure_stops():
    """Chuong van loi sau khi dich lai: dung han, khong dich chuong sau, khong ghi chuong loi."""
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        with open(raw, "w", encoding="utf-8") as f:
            f.write("=== TRUYỆN ===\n\n")
            for i in range(1, 4):
                write_chapter(f, f"第{i}章", f"Goc {i}")
        out = os.path.join(d, "raw.txt.viet.txt")
        attempts = []

        def flaky(chapter, *args, chapter_idx=None, **kwargs):
            attempts.append(chapter_idx)
            if chapter_idx == 2 and attempts.count(2) < 3:
                raise ValueError("Ban dich khong khop so doan")
            return {"title": "Tên", "paragraphs": ["Viet"], "new_terms": {}, "idioms": {},
                    "term_warnings": [], "usage": {}}

        def always_bad(chapter, *args, chapter_idx=None, **kwargs):
            attempts.append(chapter_idx)
            raise ValueError("Ban dich con sot chu Han")

        original = dt.translate_chapter
        try:
            # Lan 3 moi dung: dich lai tu dong cuu duoc, khong dung
            dt.translate_chapter = flaky
            failed = dt.translate_novel_stream(iter_chapters_from_file(raw), out, None, "k",
                                               avoid_peak=False, max_chapters=2, log=lambda *_: None)
            assert failed == [] and attempts == [1, 2, 2, 2], (failed, attempts)
            # Loi ca 3 lan: dung han o chuong 3
            attempts.clear()
            dt.translate_chapter = always_bad
            failed = dt.translate_novel_stream(iter_chapters_from_file(raw), out, None, "k",
                                               avoid_peak=False, log=lambda *_: None)
        finally:
            dt.translate_chapter = original
        assert [f["index"] for f in failed] == [3], failed
        assert attempts == [3, 3, 3], attempts
        assert [c["title"] for c in parse_chapters(out)] == ["TRUYỆN", "Chương 1: Tên", "Chương 2: Tên"]
    print("PASS stream: chuong loi tu dich lai toi 3 lan; van loi thi dung han, khong ghi chuong loi")


def test_review_glossary():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "g.json")
        dt.save_glossary(path, {"張如胞": "Trương Như Bằng", "張如鵬": "Trương Như Bằng",
                                "分局": "phân cục", "洛寧市": "thành phố Lạc Ninh"})
        issues = dt.review_glossary(path, log=lambda *_: None)
        assert len(issues) == 2, issues
        assert any("張如胞 / 張如鵬" in i for i in issues) and any("分局" in i for i in issues), issues
    print("PASS glossary: bao trung cach dich va tu thuong bi ep thanh ten")


if __name__ == "__main__":
    test_source_numbers()
    test_batch_labels_follow_source()
    test_stream_skips_done_and_continues()
    test_stream_quality_failure_stops()
    test_review_glossary()
