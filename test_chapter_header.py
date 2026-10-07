"""Kiem tra xu ly muc tieu de rong, khong goi API that.

Chay: .venv\\Scripts\\python test_chapter_header.py
"""

import os
import tempfile
import zipfile

import build_epub as build_epub_module
import deepseek_translate
from crawler import CHAPTER_SEP, count_chapters, is_novel_title_entry, parse_chapters
from validator import validate_translation


RAW_TEXT = """=== TRUYỆN ===

=== 第01章 Mở đầu ===

Đoạn gốc một.

========================================

=== 第02章 Tiếp theo ===

Đoạn gốc hai.

========================================

=== 第03章 Kết thúc ===

Đoạn gốc ba.

========================================

"""


def write_chapter(path, title, paragraphs):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"=== {title} ===\n\n")
        for paragraph in paragraphs:
            f.write(f"{paragraph}\n\n")
        f.write(CHAPTER_SEP)


def demo():
    with tempfile.TemporaryDirectory() as directory:
        raw_path = os.path.join(directory, "raw.txt")
        output_path = os.path.join(directory, "translated.txt")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(RAW_TEXT)

        chapters = parse_chapters(raw_path)
        assert len(chapters) == 4, chapters
        assert is_novel_title_entry(chapters, 0) is True
        assert is_novel_title_entry(chapters, 1) is False
        assert is_novel_title_entry([chapters[0], {"title": "Rong", "paragraphs": []}], 1) is False

        translated_indexes = []
        api_calls = []
        original_translate = deepseek_translate.translate_chapter
        original_call = deepseek_translate.call_deepseek

        def fake_translate(chapter, *args, chapter_idx=None, **kwargs):
            translated_indexes.append(chapter_idx)
            return {
                "title": f"Chương {chapter_idx}",
                "paragraphs": [f"Bản dịch {chapter_idx}."],
                "new_terms": {}, "idioms": {}, "term_warnings": [], "usage": {},
            }

        def fake_call(*args, **kwargs):
            api_calls.append((args, kwargs))
            raise AssertionError("Khong duoc goi DeepSeek cho test offline")

        deepseek_translate.translate_chapter = fake_translate
        deepseek_translate.call_deepseek = fake_call
        try:
            deepseek_translate.translate_novel(
                raw_path, output_path, None, "fake-api-key", style_detect=False,
                prepare=False, avoid_peak=False, log=lambda message: None,
            )
        finally:
            deepseek_translate.translate_chapter = original_translate
            deepseek_translate.call_deepseek = original_call

        translated = parse_chapters(output_path)
        assert translated_indexes == [1, 2, 3], translated_indexes
        assert api_calls == [], api_calls
        assert translated[0] == {"title": "TRUYỆN", "paragraphs": []}
        assert [chapter["title"] for chapter in translated[1:]] == ["Chương 1", "Chương 2", "Chương 3"]
        assert count_chapters(output_path) == 4

        resume_output = os.path.join(directory, "resume.txt")
        write_chapter(resume_output, "TRUYỆN", [])
        write_chapter(resume_output, "Chương 1", ["Bản dịch 1."])
        write_chapter(resume_output, "Chương 2", ["Bản dịch 2."])
        deepseek_translate._save_cache(resume_output, 4, {
            "title": "Chương 4", "paragraphs": ["Bản dịch 3."],
            "new_terms": {}, "idioms": {}, "term_warnings": [], "usage": {},
        })

        deepseek_translate.translate_novel(
            raw_path, resume_output, None, "fake-api-key", style_detect=False,
            prepare=False, avoid_peak=False, log=lambda message: None,
        )
        resumed = parse_chapters(resume_output)
        assert count_chapters(resume_output) == 4
        assert resumed[-1]["title"] == "Chương 3", resumed[-1]

        epub_path = os.path.join(directory, "novel.epub")
        original_copy = build_epub_module.copy_to_downloads
        build_epub_module.copy_to_downloads = lambda path: None
        try:
            build_epub_module.build_epub(resume_output, epub_path, "Test", "Test")
        finally:
            build_epub_module.copy_to_downloads = original_copy
        with zipfile.ZipFile(epub_path) as archive:
            chapter_files = [name for name in archive.namelist() if "/chap_" in name and name.endswith(".xhtml")]
            assert len(chapter_files) == 3, chapter_files
            assert all("TRUYỆN" not in archive.read(name).decode("utf-8") for name in chapter_files)

        logs = []
        warnings = validate_translation(raw_path, resume_output, log=logs.append)
        assert warnings == [], warnings
        assert not any("bi rong noi dung" in message for message in logs), logs
        assert not any("So chuong khong khop" in message for message in logs), logs

    print("OK: header rong giu resume, khong goi API va khong lech chuong.")


def demo_stream():
    """Che do stream phai ghi file dich cung bo cuc voi che do thuong (muc tieu de o dau),
    neu khong chay lai bang che do thuong se lech chi so va dich trung 1 chuong."""
    def chapters_from(raw):
        return iter([c for c in parse_chapters(raw) if c["paragraphs"]])

    def run_stream(raw, out, generator):
        indexes = []
        original = deepseek_translate.translate_chapter

        def fake_translate(chapter, *args, chapter_idx=None, **kwargs):
            indexes.append(chapter_idx)
            return {
                "title": f"Chương {chapter_idx}", "paragraphs": [f"Bản dịch {chapter_idx}."],
                "new_terms": {}, "idioms": {}, "term_warnings": [], "usage": {},
            }

        deepseek_translate.translate_chapter = fake_translate
        try:
            deepseek_translate.translate_novel_stream(
                generator, out, None, "fake-api-key", log=lambda message: None)
        finally:
            deepseek_translate.translate_chapter = original
        return indexes

    with tempfile.TemporaryDirectory() as directory:
        raw_path = os.path.join(directory, "raw.txt")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(RAW_TEXT)
        real = [c for c in parse_chapters(raw_path) if c["paragraphs"]]

        # Stream moi: file dich phai co muc tieu de o dau, chuong that danh so tu 1
        out = os.path.join(directory, "stream.txt")
        indexes = run_stream(raw_path, out, iter(real[:2]))
        assert indexes == [1, 2], indexes
        translated = parse_chapters(out)
        assert [c["title"] for c in translated] == ["TRUYỆN", "Chương 1", "Chương 2"], translated
        assert translated[0]["paragraphs"] == []
        assert count_chapters(out) == 3

        # Doi sang che do thuong tren cung cap file: chi con dich chuong thu 3, khong dich trung
        original = deepseek_translate.translate_chapter
        calls = []

        def fake_translate(chapter, *args, chapter_idx=None, **kwargs):
            calls.append((chapter["title"], chapter_idx))
            return {"title": f"Chương {chapter_idx}", "paragraphs": ["Bản dịch 3."],
                    "new_terms": {}, "idioms": {}, "term_warnings": [], "usage": {}}

        deepseek_translate.translate_chapter = fake_translate
        try:
            deepseek_translate.translate_novel(
                raw_path, out, None, "fake-api-key", style_detect=False,
                prepare=False, avoid_peak=False, log=lambda message: None)
        finally:
            deepseek_translate.translate_chapter = original
        assert calls == [("第03章 Kết thúc", 3)], calls
        assert [c["title"] for c in parse_chapters(out)] == ["TRUYỆN", "Chương 1", "Chương 2", "Chương 3"]

        # Stream tiep tuc tren file cu (dinh dang cu, khong co muc tieu de): giu nguyen cach danh so
        legacy = os.path.join(directory, "legacy.txt")
        write_chapter(legacy, "Chương 1", ["Bản dịch 1."])
        write_chapter(legacy, "Chương 2", ["Bản dịch 2."])
        indexes = run_stream(raw_path, legacy, iter(real[2:]))
        assert indexes == [3], indexes
        assert [c["title"] for c in parse_chapters(legacy)] == ["Chương 1", "Chương 2", "Chương 3"]

    print("OK: stream ghi muc tieu de nhu che do thuong, doi che do khong dich trung, file cu giu nguyen.")


if __name__ == "__main__":
    demo()
    demo_stream()
