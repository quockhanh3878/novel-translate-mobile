"""Offline tests for source adapters and crawler routing."""

import os
import tempfile
from pathlib import Path

import crawler
from sources import UukanshuAdapter, find_adapter


BASE = Path(__file__).parent / "test_data" / "uukanshu"
CATALOG_URL = "https://uukanshu.cc/book/11966/"
CHAPTER_1_URL = "https://uukanshu.cc/book/11966/7364613.html"
CHAPTER_2_URL = "https://uukanshu.cc/book/11966/7364614.html"


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


def fixture_adapter():
    paths = {
        CATALOG_URL: BASE / "book_11966.html",
        CHAPTER_1_URL: BASE / "chapter_7364613.html",
        CHAPTER_2_URL: BASE / "chapter_7364614.html",
    }

    def fetch(url):
        if url not in paths:
            return FakeResponse(b"", status_code=404)
        return FakeResponse(paths[url].read_bytes())

    return UukanshuAdapter(fetcher=fetch)


def test_adapter_selection_and_catalog():
    assert find_adapter(CATALOG_URL) is not None
    assert find_adapter("https://www.uukanshu.cc/book/11966/") is not None
    assert find_adapter("https://example.com/book/11966/") is None

    chapters = fixture_adapter().list_chapters(CATALOG_URL, log=lambda _: None)
    assert len(chapters) == 902, len(chapters)
    assert len({chapter["url"] for chapter in chapters}) == 902
    assert chapters[0]["url"].endswith("/7364613.html")
    assert chapters[-1]["url"].endswith("/11549171.html")
    assert chapters[0]["title"] == "\u7b2c\u4e00\u7ae0 \u904a\u6232\u8f09\u5165\u4e2d"


def test_adapter_chapter_parser():
    adapter = fixture_adapter()
    first = adapter.crawl_chapter(CHAPTER_1_URL, log=lambda _: None)
    second = adapter.crawl_chapter(CHAPTER_2_URL, log=lambda _: None)
    assert first["title"] == "\u7b2c\u4e00\u7ae0 \u904a\u6232\u8f09\u5165\u4e2d"
    assert second["title"] == "\u7b2c\u4e8c\u7ae0 \u652f\u7dda\u4efb\u52d9"
    assert len(first["paragraphs"]) > 20
    assert len(second["paragraphs"]) > 20
    assert all("loadAdv" not in paragraph for paragraph in first["paragraphs"])
    assert all("loadAdv" not in paragraph for paragraph in second["paragraphs"])


class StubAdapter:
    def __init__(self, chapters, results=None):
        self.chapters = chapters
        self.results = results or {}
        self.fetched = []
        self.list_calls = 0

    def list_chapters(self, start_url, log=print):
        self.list_calls += 1
        return self.chapters

    def find_start_index(self, start_url, chapters, log=print):
        for index, chapter in enumerate(chapters):
            if chapter["url"] == start_url:
                return index
        return 0

    def crawl_chapter(self, url, log=print):
        self.fetched.append(url)
        return self.results.get(url)


def make_chapters(count=4):
    return [
        {"url": f"https://uukanshu.cc/book/1/{100 + i}.html", "title": f"Chapter {i + 1}"}
        for i in range(count)
    ]


def make_result(index):
    return {"title": f"Chapter {index + 1}", "paragraphs": [f"Text {index + 1}"]}


def run_with_adapter(callback, adapter):
    old_find = crawler.find_adapter
    old_sleep = crawler.time.sleep
    old_uniform = crawler.random.uniform
    crawler.find_adapter = lambda _: adapter
    crawler.time.sleep = lambda _: None
    crawler.random.uniform = lambda *_: 0
    try:
        return callback()
    finally:
        crawler.find_adapter = old_find
        crawler.time.sleep = old_sleep
        crawler.random.uniform = old_uniform


def test_resume_and_chapter_start():
    chapters = make_chapters()
    adapter = StubAdapter(chapters, {chapters[2]["url"]: make_result(2)})
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "resume.txt")
        with open(output, "w", encoding="utf-8") as handle:
            handle.write("=== TRUYEN ===\n\n")
            handle.write("=== Chapter 1 ===\n\nText\n\n" + crawler.CHAPTER_SEP)
            handle.write("=== Chapter 2 ===\n\nText\n\n" + crawler.CHAPTER_SEP)

        saved = run_with_adapter(
            lambda: crawler.crawl_novel(
                chapters[3]["url"], output, log=lambda _: None,
                should_stop=lambda: len(adapter.fetched) >= 1,
            ),
            adapter,
        )
        assert saved == 1
        assert adapter.fetched == [chapters[2]["url"]]
        assert crawler.count_chapters(output) == 3

    adapter = StubAdapter(chapters, {chapters[1]["url"]: make_result(1)})
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "chapter-start.txt")
        saved = run_with_adapter(
            lambda: crawler.crawl_novel(
                chapters[1]["url"], output, log=lambda _: None,
                should_stop=lambda: len(adapter.fetched) >= 1,
            ),
            adapter,
        )
        assert saved == 1
        assert adapter.fetched == [chapters[1]["url"]]


def test_stream_limit_end_and_errors():
    chapters = make_chapters()
    results = {chapter["url"]: make_result(i) for i, chapter in enumerate(chapters)}
    adapter = StubAdapter(chapters, results)
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "stream.txt")

        def collect():
            return list(crawler.crawl_chapters_stream(
                CATALOG_URL, output, max_chapters=2, log=lambda _: None,
            ))

        streamed = run_with_adapter(collect, adapter)
        assert len(streamed) == 2
        assert crawler.count_chapters(output) == 2

    last = StubAdapter(chapters, {chapters[-1]["url"]: make_result(3)})
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "last.txt")
        saved = run_with_adapter(
            lambda: crawler.crawl_novel(
                chapters[-1]["url"], output, log=lambda _: None,
            ),
            last,
        )
        assert saved == 1
        assert last.fetched == [chapters[-1]["url"]]

    errors = StubAdapter(chapters, {})
    errors.crawl_chapter = lambda url, log=print: (errors.fetched.append(url) or False)
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "errors.txt")
        saved = run_with_adapter(
            lambda: crawler.crawl_novel(CATALOG_URL, output, log=lambda _: None),
            errors,
        )
        assert saved == 0
        assert len(errors.fetched) == 4
        assert crawler.count_chapters(output) == 0


def test_legacy_url_path():
    old_find = crawler.find_adapter
    old_crawl = crawler.crawl_chapter
    old_sleep = crawler.time.sleep
    fetched = []
    crawler.find_adapter = lambda _: None
    crawler.time.sleep = lambda _: None

    def fake_crawl(url, log=print):
        fetched.append(url)
        return None

    crawler.crawl_chapter = fake_crawl
    try:
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "legacy.txt")
            with open(output, "w", encoding="utf-8") as handle:
                handle.write("=== Chapter 1 ===\n\nText\n\n" + crawler.CHAPTER_SEP)
                handle.write("=== Chapter 2 ===\n\nText\n\n" + crawler.CHAPTER_SEP)
            crawler.crawl_novel("https://example.com/novel_1.html", output, log=lambda _: None)
    finally:
        crawler.find_adapter = old_find
        crawler.crawl_chapter = old_crawl
        crawler.time.sleep = old_sleep

    assert fetched == ["https://example.com/novel_3.html"]


def main():
    test_adapter_selection_and_catalog()
    test_adapter_chapter_parser()
    test_resume_and_chapter_start()
    test_stream_limit_end_and_errors()
    test_legacy_url_path()
    print("OK: uukanshu adapter and crawler routing tests passed.")


if __name__ == "__main__":
    main()
