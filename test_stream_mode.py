"""Kiem tra gioi han dich moi va bo qua chuong da dich trong che do stream."""

import os
import tempfile

import deepseek_translate
from crawler import CHAPTER_SEP, iter_chapters_from_file, parse_chapters


def write_chapter(handle, title, text):
    handle.write(f"=== {title} ===\n\n{text}\n\n{CHAPTER_SEP}")


def demo():
    with tempfile.TemporaryDirectory() as directory:
        raw_path = os.path.join(directory, "raw.txt")
        with open(raw_path, "w", encoding="utf-8") as handle:
            handle.write("=== TRUYỆN ===\n\n")
            for index in range(1, 11):
                write_chapter(handle, f"第{index}章", f"Goc {index}")

        translated_path = os.path.join(directory, "raw.txt.viet.txt")
        with open(translated_path, "w", encoding="utf-8") as handle:
            write_chapter(handle, "TRUYỆN", "")
            write_chapter(handle, "Chương 8", "Da dich 8")

        calls = []
        consumed = []
        original = deepseek_translate.translate_chapter

        def source_chapters():
            for chapter in iter_chapters_from_file(raw_path):
                consumed.append(chapter["_source_index"])
                yield chapter

        def fake_translate(chapter, *args, chapter_idx=None, **kwargs):
            calls.append((chapter_idx, chapter["title"]))
            return {
                "title": f"Chương {chapter_idx}",
                "paragraphs": [f"Viet {chapter_idx}"],
                "new_terms": {},
                "idioms": {},
                "term_warnings": [],
                "usage": {},
            }

        deepseek_translate.translate_chapter = fake_translate
        try:
            deepseek_translate.translate_novel_stream(
                source_chapters(),
                translated_path,
                None,
                "fake-api-key",
                avoid_peak=False,
                max_chapters=8,
                log=lambda message: None,
            )
        finally:
            deepseek_translate.translate_chapter = original

        assert [index for index, _ in calls] == [1, 2, 3, 4, 5, 6, 7, 9], calls
        assert 8 not in [index for index, _ in calls], calls
        assert consumed == [1, 2, 3, 4, 5, 6, 7, 8, 9], consumed
        titles = [chapter["title"] for chapter in parse_chapters(translated_path)]
        assert titles.count("Chương 8") == 1, titles
        assert titles == ["TRUYỆN"] + [f"Chương {index}" for index in range(1, 10)], titles
        assert len(titles) == 10, titles

    print("OK: stream dich du 8 chuong moi, bo qua chuong 8 da co.")


if __name__ == "__main__":
    demo()
