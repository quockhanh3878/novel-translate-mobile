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


def _old_file(d, titles_):
    raw = os.path.join(d, "raw.txt")
    with open(raw, "w", encoding="utf-8") as f:
        f.write("=== TRUYỆN ===\n\n")
        for t in titles_:
            crawler._write_chapter(f, {"title": t, "paragraphs": ["x"]})
    return raw  # khong co .progress.json, giong file cao tu ban cu


def test_adapter_old_file_title_differs_uses_chapter_number():
    # File cu thieu chuong 3 (4 muc, chuong cuoi la 第5章); ten trong muc luc khac ten da luu.
    catalog = [{"url": f"https://x/c{i}", "title": f"第{i}章 标题{i}"} for i in range(1, 9)]
    adapter = FakeAdapter(catalog)
    with tempfile.TemporaryDirectory() as d:
        raw = _old_file(d, ["第1章　标题1（求票）", "第2章", "第4章", "第5章　标题5（求票）"])
        assert crawler._adapter_resume_index(raw, catalog, 4, 0, lambda *_: None) == 5
        fetched = []
        crawler.crawl_chapter = lambda url, log=print: (fetched.append(url) or {
            "title": next(c["title"] for c in catalog if c["url"] == url), "paragraphs": ["x"]})
        run(crawler._crawl_novel_with_adapter, "https://x/c1", raw, adapter, lambda *_: None, None)
        assert fetched[0] == "https://x/c6", fetched
        assert titles(raw)[4:] == ["第6章 标题6", "第7章 标题7", "第8章 标题8"], titles(raw)


def test_adapter_empty_chapter_skipped_not_stuck():
    """1 muc muc luc khong co noi dung khong duoc chan ca truyen; nhieu muc lien tiep thi dung."""
    catalog = [{"url": f"https://x/c{i}", "title": f"第{i}章"} for i in range(1, 10)]
    adapter = FakeAdapter(catalog)
    with tempfile.TemporaryDirectory() as d:
        raw = _old_file(d, ["第1章", "第2章"])
        crawler._save_last_url(raw, "https://x/c2")
        empty = {"https://x/c3", "https://x/c6", "https://x/c7", "https://x/c8", "https://x/c9"}
        crawler.crawl_chapter = lambda url, log=print: None if url in empty else {
            "title": next(c["title"] for c in catalog if c["url"] == url), "paragraphs": ["x"]}
        run(crawler._crawl_novel_with_adapter, "https://x/c1", raw, adapter, lambda *_: None, None)
        assert titles(raw) == ["第1章", "第2章", "第4章", "第5章"], titles(raw)
        assert crawler._load_last_url(raw) == "https://x/c5"


def test_legacy_old_file_missing_chapters_no_duplicate():
    # File cu thieu chuong 3 -> 4 muc nhung chuong cuoi la 第5章 (trang _5). Doan theo so chuong
    # se tai trang _5 (da co): phai bo qua, khong ghi trung.
    pages = {n: f"第{n}章" for n in range(1, 8)}
    with tempfile.TemporaryDirectory() as d:
        raw = _old_file(d, ["第1章", "第2章", "第4章", "第5章"])
        crawler.crawl_chapter = lambda url, log=print: (
            lambda n: {"title": pages[n], "paragraphs": ["x"]} if n in pages else None
        )(int(url.rsplit("_", 1)[1].split(".")[0]))
        run(crawler.crawl_novel, "https://w/novel_1.html", raw, lambda *_: None, None)
        assert titles(raw) == ["第1章", "第2章", "第4章", "第5章", "第6章", "第7章"], titles(raw)


def test_adapter_volume_restart_picks_nearest_match():
    # Quyen 2 danh so lai: 第2章 xuat hien 2 lan; file moi co 2 chuong -> la 第2章 cua quyen 1.
    catalog = [{"url": f"https://x/v{v}c{i}", "title": f"第{i}章"} for v in (1, 2) for i in range(1, 4)]
    with tempfile.TemporaryDirectory() as d:
        raw = _old_file(d, ["第1章", "第2章"])
        assert crawler._adapter_resume_index(raw, catalog, 2, 0, lambda *_: None) == 2


def test_from_chapter_overrides_saved_position():
    # Vi tri da luu bi sai (chi vao chuong 2) nhung nguoi dung chon cao tu chuong 6.
    catalog = [{"url": f"https://x/c{i}", "title": f"第{i}章"} for i in range(1, 9)]
    catalog.insert(2, {"url": "https://x/notice", "title": "公告"})
    adapter = FakeAdapter(catalog)
    with tempfile.TemporaryDirectory() as d:
        raw = _old_file(d, ["第1章", "第2章", "第3章", "第4章"])
        crawler._save_last_url(raw, "https://x/c2")
        fetched = []
        crawler.crawl_chapter = lambda url, log=print: (fetched.append(url) or {
            "title": next(c["title"] for c in catalog if c["url"] == url), "paragraphs": ["x"]})
        run(crawler._crawl_novel_with_adapter, "https://x/c1", raw, adapter, lambda *_: None, None, 6)
        assert fetched[0] == "https://x/c6", fetched
        assert titles(raw)[4:] == ["第6章", "第7章", "第8章"], titles(raw)
        # Che do stream (cao + dich): cung bat dau tu chuong chon
        fetched.clear()
        crawler.crawl_chapter = lambda url, log=print: (fetched.append(url) or {
            "title": next(c["title"] for c in catalog if c["url"] == url), "paragraphs": ["x"]})
        crawler.find_adapter, old_find = (lambda url: adapter), crawler.find_adapter
        try:
            run(lambda: list(crawler.crawl_chapters_stream(
                "https://x/c1", os.path.join(d, "s.txt"), log=lambda *_: None, from_chapter=7)))
        finally:
            crawler.find_adapter = old_find
        assert fetched[0] == "https://x/c7", fetched
        # Chuong 6 bi xoa khoi muc luc -> lay chuong co so lon hon gan nhat
        assert crawler._from_chapter_index([c for c in catalog if c["title"] != "第6章"], 6, lambda *_: None) == 6
        # Muc luc khong danh so -> theo thu tu
        assert crawler._from_chapter_index([{"url": "a", "title": "x"}] * 5, 3, lambda *_: None) == 2


def test_from_chapter_legacy_and_stream():
    # Giong wa01: trang _N lech so chuong (第13章 o trang _25), co trang thong bao xen giua.
    pages = {p: f"第{p - 12}章" for p in range(13, 31)}
    pages[20] = "公告"
    pages.update({p: f"第{p - 13}章" for p in range(21, 31)})
    fetched = []

    def fake(url, log=print):
        n = int(url.rsplit("_", 1)[1].split(".")[0])
        fetched.append(n)
        return {"title": pages[n], "paragraphs": ["x"]} if n in pages else None

    with tempfile.TemporaryDirectory() as d:
        # Khong co file vi tri: doan trang _13, do theo do lech toi trang _25
        raw = _old_file(d, ["第1章", "第2章"])
        crawler.crawl_chapter = fake
        run(crawler.crawl_novel, "https://w/novel_1.html", raw, lambda *_: None, None, 12)
        assert titles(raw)[2:5] == ["第12章", "第13章", "第14章"], (fetched, titles(raw))
        assert fetched[:5] == [12, 13, 24, 25, 25], fetched  # 3 trang do tim roi cao tu _25

        # Co file vi tri (第1章 o _13): doan theo do lech, do them 1 trang vi thong bao xen giua
        raw2 = os.path.join(d, "s.txt")
        with open(raw2, "w", encoding="utf-8") as f:
            crawler._write_chapter(f, {"title": "第1章", "paragraphs": ["x"]})
        crawler._save_last_url(raw2, "https://w/novel_13.html")
        fetched.clear()
        crawler.crawl_chapter = fake
        out = run(lambda: list(crawler.crawl_chapters_stream(
            "https://w/novel_1.html", raw2, log=lambda *_: None, from_chapter=16)))
        assert fetched[:3] == [28, 29, 29] and [c["title"] for c in out] == ["第16章", "第17章"], (out, fetched)

        # Chuong khong ton tai (bi xoa / so qua lon) -> khong cao trang _99 bua
        assert crawler._legacy_page_for_chapter(raw, "https://w/novel_", ".html", 99, lambda *_: None) == 99


def test_volume_restart_not_skipped():
    assert not crawler._already_saved("第1章 新卷", crawler._norm_title("第50章"))
    assert crawler._already_saved("第48章", crawler._norm_title("第50章"))
    assert not crawler._already_saved("第51章", crawler._norm_title("第50章"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
