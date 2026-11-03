"""Cao tiep phai bat dau ngay sau chuong cuoi da luu, khong suy tu so chuong trong file."""

import os
import tempfile

import crawler


class FakeAdapter:
    def __init__(self, chapters):
        self.chapters = chapters
        self.fetched = []

    def list_chapters(self, start_url, log=print):
        return self.chapters

    def find_start_index(self, start_url, chapters, log=print):
        for index, chapter in enumerate(chapters):
            if chapter["url"] == start_url:
                return index
        return 0


REAL_SLEEP, REAL_CRAWL = crawler.time.sleep, crawler.crawl_chapter


def run(fn, *args, **kwargs):
    crawler.time.sleep = lambda *_: None
    try:
        return fn(*args, **kwargs)
    finally:
        crawler.time.sleep, crawler.crawl_chapter = REAL_SLEEP, REAL_CRAWL


def titles(path):
    return [c["title"] for c in crawler.iter_chapters_from_file(path)]


def test_adapter_resume_from_mid_start():
    # Muc luc co trang thong bao xen giua, lan dau cao tu chuong 6 -> so chuong trong file khong khop chi so.
    catalog = [{"url": f"https://x/c{i}", "title": f"第{i}章"} for i in range(1, 11)]
    catalog.insert(3, {"url": "https://x/notice", "title": "公告"})
    adapter = FakeAdapter(catalog)
    fetched = []

    def fake_crawl(url, log=print):
        fetched.append(url)
        return {"title": next(c["title"] for c in catalog if c["url"] == url), "paragraphs": ["x"]}

    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        crawler.crawl_chapter = fake_crawl
        stops = iter([False, False, True])
        run(crawler._crawl_novel_with_adapter, "https://x/c6", raw, adapter, lambda *_: None, lambda: next(stops))
        assert titles(raw) == ["第6章", "第7章", "第8章"], titles(raw)
        crawler.crawl_chapter = fake_crawl
        run(crawler._crawl_novel_with_adapter, "https://x/c6", raw, adapter, lambda *_: None, None)
        assert titles(raw) == [f"第{i}章" for i in range(6, 11)], titles(raw)


def test_adapter_old_file_without_progress_uses_last_title():
    catalog = [{"url": f"https://x/c{i}", "title": f"第{i}章"} for i in range(1, 8)]
    catalog.insert(1, {"url": "https://x/notice", "title": "公告"})
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        with open(raw, "w", encoding="utf-8") as f:
            f.write("=== TRUYỆN ===\n\n")
            for i in range(1, 5):
                crawler._write_chapter(f, {"title": f"第{i}章", "paragraphs": ["x"]})
        # 4 chuong trong file, nhung chuong 4 nam o vi tri 5 trong muc luc.
        assert crawler._adapter_resume_index(raw, catalog, 4, 0, lambda *_: None) == 5


def test_adapter_skips_chapter_written_before_progress_saved():
    catalog = [{"url": f"https://x/c{i}", "title": f"第{i}章"} for i in range(1, 6)]
    adapter = FakeAdapter(catalog)
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        with open(raw, "w", encoding="utf-8") as f:
            f.write("=== TRUYỆN ===\n\n")
            for i in range(1, 4):
                crawler._write_chapter(f, {"title": f"第{i}章", "paragraphs": ["x"]})
        crawler._save_last_url(raw, "https://x/c2")  # vi tri cham hon file 1 chuong
        crawler.crawl_chapter = lambda url, log=print: {
            "title": next(c["title"] for c in catalog if c["url"] == url), "paragraphs": ["x"]}
        run(crawler._crawl_novel_with_adapter, "https://x/c1", raw, adapter, lambda *_: None, None)
        assert titles(raw) == [f"第{i}章" for i in range(1, 6)], titles(raw)


def test_legacy_resume_by_index_and_skip_missing_pages():
    pages = {1: "第1章", 2: "第2章", 4: "第3章", 5: "第4章", 6: "第5章"}  # trang _3 khong ton tai
    fetched = []

    def fake_crawl(url, log=print):
        n = int(url.rsplit("_", 1)[1].split(".")[0])
        fetched.append(n)
        return {"title": pages[n], "paragraphs": ["x"]} if n in pages else None

    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        crawler.crawl_chapter = fake_crawl
        stops = iter([False, False, True])
        run(crawler.crawl_novel, "https://w/novel_1.html", raw, lambda *_: None, lambda: next(stops))
        assert titles(raw) == ["第1章", "第2章", "第3章"], titles(raw)
        # 3 chuong trong file nhung chuong cuoi o trang _4: phai cao tiep tu _5, khong phai _4.
        fetched.clear()
        crawler.crawl_chapter = fake_crawl
        run(crawler.crawl_novel, "https://w/novel_1.html", raw, lambda *_: None, None)
        assert fetched[0] == 5, fetched
        assert titles(raw) == ["第1章", "第2章", "第3章", "第4章", "第5章"], titles(raw)


def test_stream_source_index_is_file_position():
    catalog = [{"url": f"https://x/c{i}", "title": f"第{i}章"} for i in range(1, 6)]
    catalog.insert(1, {"url": "https://x/notice", "title": "公告"})
    adapter = FakeAdapter(catalog)
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw.txt")
        crawler.crawl_chapter = lambda url, log=print: {
            "title": next(c["title"] for c in catalog if c["url"] == url), "paragraphs": ["x"]}
        out = run(lambda: list(crawler._crawl_stream_with_adapter(
            "https://x/c3", raw, 0, adapter, lambda *_: None, None, from_start=True)))
        # Bat dau tu giua muc luc: chi so phai la vi tri trong file (1..3), khong phai vi tri muc luc.
        assert [c["_source_index"] for c in out] == [1, 2, 3], out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
