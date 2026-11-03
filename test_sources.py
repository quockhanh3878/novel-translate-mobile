"""Offline tests for source adapters and crawler routing."""

import os
import tempfile
from pathlib import Path

import crawler
from sources import (
    Bgq99Adapter,
    BiqugeTwAdapter,
    Shuba69Adapter,
    ShubaowAdapter,
    TianyaBooksAdapter,
    UukanshuAdapter,
    find_adapter,
    parse_saved_chapter_html,
)


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


def test_saved_html_import_and_challenge_detection():
    html = """
    <html><head><title>Book</title></head><body>
      <div class="title">Chapter 12</div>
      <div class="content"><p>First paragraph with enough text.</p>
      <p>Second paragraph.</p><div class="mobadsq">advertisement</div>
      <a class="anchor_bookmark">bookmark</a></div>
    </body></html>
    """
    chapter = parse_saved_chapter_html(html, "book_12.html")
    assert chapter == {
        "title": "Chapter 12",
        "paragraphs": ["First paragraph with enough text.", "Second paragraph."],
    }, chapter

    mhtml = """MIME-Version: 1.0
Content-Type: multipart/related; boundary="part"

--part
Content-Type: text/html; charset="utf-8"
Content-Transfer-Encoding: quoted-printable

<div class=3D"title">Chapter 13</div><div class=3D"content"><p>A saved MHTML chapter with enough text to import.</p></div>
--part--
"""
    mhtml_chapter = parse_saved_chapter_html(mhtml, "book_13.mhtml")
    assert mhtml_chapter["title"] == "Chapter 13"
    assert mhtml_chapter["paragraphs"] == ["A saved MHTML chapter with enough text to import."]

    try:
        parse_saved_chapter_html(
            '<html><body><div id="error">challenge_required</div></body></html>',
            "blocked.html",
        )
    except ValueError as exc:
        assert "xac minh" in str(exc)
    else:
        raise AssertionError("A saved challenge page must not be accepted as chapter content.")


def test_wa01_http_block_stops_for_manual_import():
    class FakeResponse:
        status_code = 403

    class FakeScraper:
        def get(self, *args, **kwargs):
            return FakeResponse()

    original_create_scraper = crawler.cloudscraper.create_scraper
    crawler.cloudscraper.create_scraper = lambda **_: FakeScraper()
    messages = []
    try:
        try:
            crawler.crawl_chapter(
                "https://www.wa01.com/novel/pagea/sample_1.html", log=messages.append,
            )
        except crawler.CrawlBlockedError as exc:
            assert "HTTP 403" in str(exc)
            assert "nhap file HTML" in str(exc)
        else:
            raise AssertionError("HTTP 403 must stop without retrying as a chapter parse failure.")
    finally:
        crawler.cloudscraper.create_scraper = original_create_scraper


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

    assert fetched == [f"https://example.com/novel_{n}.html" for n in range(3, 4 + crawler.MAX_MISSING_INDEXES)]


def test_bgq99_adapter():
    for url in (
        "https://www.bgq99.cc/book/1217966/",
        "https://bgq99.cc/book/1217966/",
        "https://m.bgq99.cc/book/1217966/616859768.html",
    ):
        adapter = find_adapter(url)
        assert isinstance(adapter, Bgq99Adapter), url

    catalog_html = """
    <html><body>
      <div class="small"><span class="last"><a href="/book/1217966/74638527.html">第3249章</a></span></div>
      <div class="listmain">
        <dl>
          <dt>《红色莫斯科》最新章节</dt>
          <dd><a href="/book/1217966/74638527.html">第3249章 终章</a></dd>
          <dt>《红色莫斯科》正文</dt>
          <dd><a href="/book/1217966/616859768.html">第1章 希姆基镇</a></dd>
          <dd><a href="/book/1217966/616761558.html">第2章 示警</a></dd>
        </dl>
      </div>
    </body></html>
    """.encode("utf-8")

    chapter_html = """
    <html><body>
      <div class="content">
        <h1>第1章 希姆基镇</h1>
        <div class="textinfo"><span>小说：<a href="/book/1217966/">红色莫斯科</a></span><span>作者：涂抹记忆</span></div>
        <div class="showtxt" id="content">
          　　林华穿着一身苏军卫国战争时期的套头军装。<br/><br/>
          　　我想，人民委员同志可能正和派出所所长在吃午饭呢。请记住本书首发域名：www.bgq99.cc。<br/><br/>
          　　请记住本书首发域名：www.bgq99.cc。顶点小说网手机版更新最快网址：m.bgq99.cc
        </div>
        <div class="page_chapter"><ul><li><a href="/book/1217966/616761558.html">下一章</a></li></ul></div>
      </div>
    </body></html>
    """.encode("utf-8")

    pages = {
        "https://www.bgq99.cc/book/1217966/": FakeResponse(catalog_html),
        "https://www.bgq99.cc/book/1217966/616859768.html": FakeResponse(chapter_html),
    }
    adapter = Bgq99Adapter(fetcher=lambda u: pages.get(u, FakeResponse(b"", status_code=404)))
    chapters = adapter.list_chapters("https://m.bgq99.cc/book/1217966/", log=lambda _: None)
    assert chapters == [
        {"url": "https://www.bgq99.cc/book/1217966/616859768.html", "title": "第1章 希姆基镇"},
        {"url": "https://www.bgq99.cc/book/1217966/616761558.html", "title": "第2章 示警"},
    ], chapters

    ch1 = adapter.crawl_chapter("https://m.bgq99.cc/book/1217966/616859768.html", log=lambda _: None)
    assert ch1 == {
        "title": "第1章 希姆基镇",
        "paragraphs": [
            "林华穿着一身苏军卫国战争时期的套头军装。",
            "我想，人民委员同志可能正和派出所所长在吃午饭呢。",
        ],
    }, ch1


def test_shuba69_adapter():
    for url in (
        "https://www.69shuba.com/book/90175.htm",
        "https://www.69shuba.com/book/90175/",
        "https://69shuba.com/txt/90175/40587865",
    ):
        adapter = find_adapter(url)
        assert isinstance(adapter, Shuba69Adapter), url

    assert adapter.is_catalog_url("https://www.69shuba.com/book/90175.htm") is True
    assert adapter.is_catalog_url("https://www.69shuba.com/book/90175/") is True
    assert adapter.is_catalog_url("https://www.69shuba.com/txt/90175/40587865") is False

    catalog_html = """
    <html><body>
      <div class="catalog">
        <h3>书签</h3>
        <ul><li data-num="7"><a id="bookcase" href="#"></a></li></ul>
      </div>
      <div class="catalog" id="catalog" data-eid="0">
        <ul>
          <li data-num="2"><a href="https://www.69shuba.com/txt/90175/40587866">第2章 救赎轮盘</a></li>
          <li data-num="1"><a href="https://www.69shuba.com/txt/90175/40587865">第1章 一次测试</a></li>
        </ul>
      </div>
    </body></html>
    """.encode("gb18030")

    chapter_html = """
    <html><body>
      <div class="txtnav">
        <h1 class="hide720">第1章 一次测试</h1>
        <div class="txtinfo hide720"><span>2025-12-10</span> <span>作者： 青衫取醉</span></div>
        <div id="txtright"><script>loadAdv(2, 0);</script></div>
          第1章 一次测试<br/><br/>
          【你好，林思之。】<br/><br/>
          【游戏开始。】<br/><br/>
          (本章完)<br/><br/>
        <div class="bottom-ad"><script>loadAdv(3, 0);</script></div>
      </div>
    </body></html>
    """.encode("gb18030")

    pages = {
        "https://www.69shuba.com/book/90175/": FakeResponse(catalog_html),
        "https://www.69shuba.com/txt/90175/40587865": FakeResponse(chapter_html),
    }
    adapter = Shuba69Adapter(fetcher=lambda u: pages.get(u, FakeResponse(b"", status_code=404)))
    chapters = adapter.list_chapters("https://www.69shuba.com/book/90175.htm", log=lambda _: None)
    assert chapters == [
        {"url": "https://www.69shuba.com/txt/90175/40587865", "title": "第1章 一次测试"},
        {"url": "https://www.69shuba.com/txt/90175/40587866", "title": "第2章 救赎轮盘"},
    ], chapters

    ch1 = adapter.crawl_chapter("https://69shuba.com/txt/90175/40587865", log=lambda _: None)
    assert ch1 == {
        "title": "第1章 一次测试",
        "paragraphs": [
            "【你好，林思之。】",
            "【游戏开始。】",
        ],
    }, ch1


def test_shubaow_adapter():
    for url in (
        "https://www.shubaow.net/book/378.html",
        "https://shubaow.net/book/378/",
        "https://m.shubaow.net/book/378/53641.html",
    ):
        adapter = find_adapter(url)
        assert isinstance(adapter, ShubaowAdapter), url

    assert adapter.is_catalog_url("https://www.shubaow.net/book/378.html") is True
    assert adapter.is_catalog_url("https://www.shubaow.net/book/378/") is True
    assert adapter.is_catalog_url("https://www.shubaow.net/book/378/53641.html") is False

    catalog_html = """
    <html><body>
      <div class="book-latest-episode"><a href="/book/378/53812.html">第172章</a></div>
      <div class="card" id="list-chapterAll">
        <div class="chapter-list-grid">
          <a href="/book/378/53641.html">第1章</a>
          <a href="/book/378/53642.html">第2章</a>
        </div>
      </div>
    </body></html>
    """.encode("gb18030")

    chapter_html = """
    <html><body>
      <div class="read-main-card" id="content">
        <div class="read-header">
          <h1 class="read-title">第1章</h1>
          <div class="read-meta-links"><a href="https://www.shubaow.net/book/378.html">书籍目录</a></div>
        </div>
        <div class="read-content-body" id="htmlContent">
          &nbsp;&nbsp;&nbsp;&nbsp;［提示：你又穷又丑。］<br><br>
          &nbsp;&nbsp;&nbsp;&nbsp;柳秋点了很多次。<br><br>
          &nbsp;&nbsp;&nbsp;&nbsp;开文！冲！
        </div>
        <div class="read-pager-group"><a href="53642.html">下一章</a></div>
      </div>
    </body></html>
    """.encode("gb18030")

    pages = {
        "https://www.shubaow.net/book/378.html": FakeResponse(catalog_html),
        "https://www.shubaow.net/book/378/53641.html": FakeResponse(chapter_html),
    }
    adapter = ShubaowAdapter(fetcher=lambda u: pages.get(u, FakeResponse(b"", status_code=404)))
    chapters = adapter.list_chapters("https://m.shubaow.net/book/378/", log=lambda _: None)
    assert chapters == [
        {"url": "https://www.shubaow.net/book/378/53641.html", "title": "第1章"},
        {"url": "https://www.shubaow.net/book/378/53642.html", "title": "第2章"},
    ], chapters

    ch1 = adapter.crawl_chapter("https://m.shubaow.net/book/378/53641.html", log=lambda _: None)
    assert ch1 == {
        "title": "第1章",
        "paragraphs": [
            "［提示：你又穷又丑。］",
            "柳秋点了很多次。",
            "开文！冲！",
        ],
    }, ch1


def test_biquge_tw_adapter():
    for url in (
        "https://www.biquge.tw/book/200183/",
        "https://biquge.tw/book/200183.html",
        "https://m.biquge.tw/book/200183/75125892.html",
    ):
        adapter = find_adapter(url)
        assert isinstance(adapter, BiqugeTwAdapter), url

    assert adapter.is_catalog_url("https://www.biquge.tw/book/200183/") is True
    assert adapter.is_catalog_url("https://www.biquge.tw/book/200183.html") is True
    assert adapter.is_catalog_url("https://www.biquge.tw/book/200183/75125892.html") is False

    catalog_html = """
    <html><body>
      <div class="latest"><a href="/book/200183/76409509.html">14上天无路，入地无门</a></div>
      <div class="list-chapter">
        <div class="booklist">
          <ul>
            <li><a href="/book/200183/75125892.html">第01章 问卜中州 公园邂逅</a></li>
            <li><a href="/book/200183/75125914.html">第02章 古铁神算</a></li>
          </ul>
        </div>
      </div>
    </body></html>
    """.encode("utf-8")

    chapter_html = """
    <html><body>
      <div class="book read">
        <h1>第01章 问卜中州 公园邂逅（1 / 1）</h1>
        <div class="read-page">
          <a href="/book/200183.html">上一章</a>
          <a href="/book/200183.html" rel="index">目录</a>
          <a href="/book/200183/75125914.html" rel="next">下一章</a>
        </div>
        <div class="read-content" id="chaptercontent">
          <p>太行山上太行关，出关百里不见山。</p>
          <p>民谚表述的很形象，巍巍太行在这里绵延到了尽头。</p>
          <p>如果您觉得《超级大忽悠》还不错的话，请粘贴以下网址分享给你的QQ、微信或微博好友，谢谢支持！</p>
          <p>（ ）</p>
        </div>
      </div>
    </body></html>
    """.encode("utf-8")

    pages = {
        "https://www.biquge.tw/book/200183/": FakeResponse(catalog_html),
        "https://www.biquge.tw/book/200183/75125892.html": FakeResponse(chapter_html),
    }
    adapter = BiqugeTwAdapter(fetcher=lambda u: pages.get(u, FakeResponse(b"", status_code=404)))
    chapters = adapter.list_chapters("https://m.biquge.tw/book/200183.html", log=lambda _: None)
    assert chapters == [
        {"url": "https://www.biquge.tw/book/200183/75125892.html", "title": "第01章 问卜中州 公园邂逅"},
        {"url": "https://www.biquge.tw/book/200183/75125914.html", "title": "第02章 古铁神算"},
    ], chapters

    ch1 = adapter.crawl_chapter("https://m.biquge.tw/book/200183/75125892.html", log=lambda _: None)
    assert ch1 == {
        "title": "第01章 问卜中州 公园邂逅",
        "paragraphs": [
            "太行山上太行关，出关百里不见山。",
            "民谚表述的很形象，巍巍太行在这里绵延到了尽头。",
        ],
    }, ch1

    saved = parse_saved_chapter_html(chapter_html.decode("utf-8"), "biquge_ch1.html")
    assert saved == ch1, saved


def test_tianyabooks_adapter():
    for url in (
        "https://www.tianyabooks.com/net/csx_03/27174.html",
        "https://tianyabooks.com/net/csx_03/",
        "https://m.tianyabooks.com/net/csx_03/index.html",
    ):
        adapter = find_adapter(url)
        assert isinstance(adapter, TianyaBooksAdapter), url

    assert adapter.is_catalog_url("https://www.tianyabooks.com/net/csx_03/") is True
    assert adapter.is_catalog_url("https://www.tianyabooks.com/net/csx_03/index.html") is True
    assert adapter.is_catalog_url("https://www.tianyabooks.com/net/csx_03/27174.html") is False
    assert adapter.catalog_url("https://www.tianyabooks.com/net/csx_03/27174.html") == (
        "https://www.tianyabooks.com/net/csx_03/"
    )

    catalog_html = """
    <html><body>
      <div class="catalog">
        <h1>《超级大忽悠(高人)》</h1>
        <div class="author"><a href="/net/csx_03/99999.html">不应采集</a></div>
        <div class="mulu-title"><h2>第一卷 非主流从业指南</h2></div>
        <div class="mulu-list">
          <ul>
            <li><a href="27174.html">第01章 问卜中州 公园邂逅</a></li>
            <li><a href="27175.html">第02章 古铁神算</a></li>
          </ul>
        </div>
        <div class="mulu-title"><h2>第二卷 非正规创富攻略</h2></div>
        <div class="mulu-list">
          <ul>
            <li><a href="27311.html">第01章 思维超前 生意坑爹</a></li>
          </ul>
        </div>
      </div>
    </body></html>
    """.encode("gb18030")

    chapter_html = """
    <html><body>
      <div class="content book-content">
        <h1>超级大忽悠(高人) 第一卷 非主流从业指南 第01章 问卜中州 公园邂逅</h1>
        <div class="info">所属书籍：<a href="./index.html" title="超级大忽悠(高人)">超级大忽悠(高人)</a></div>
        <div class="neirong" id="neirong">
          <p>
            &nbsp;&nbsp;&nbsp;&nbsp;太行山上太行关，出关百里不见山。<br/><br/>
            &nbsp;&nbsp;&nbsp;&nbsp;民谚表述的很形象，巍巍太行在这里绵延到了尽头。<br/><br/>
            &nbsp;&nbsp;&nbsp;&nbsp;旁座的年青一愣，也跟着所指方向看过去了。
          </p>
        </div>
        <div class="prev">上一页：<a id="BookNext" href="index.html">上一章</a></div>
      </div>
    </body></html>
    """.encode("gb18030")

    pages = {
        "https://www.tianyabooks.com/net/csx_03/": FakeResponse(catalog_html),
        "https://www.tianyabooks.com/net/csx_03/27174.html": FakeResponse(chapter_html),
    }
    adapter = TianyaBooksAdapter(fetcher=lambda u: pages.get(u, FakeResponse(b"", status_code=404)))
    chapters = adapter.list_chapters("https://www.tianyabooks.com/net/csx_03/27174.html", log=lambda _: None)
    assert chapters == [
        {"url": "https://www.tianyabooks.com/net/csx_03/27174.html", "title": "第01章 问卜中州 公园邂逅"},
        {"url": "https://www.tianyabooks.com/net/csx_03/27175.html", "title": "第02章 古铁神算"},
        {"url": "https://www.tianyabooks.com/net/csx_03/27311.html", "title": "第01章 思维超前 生意坑爹"},
    ], chapters

    assert adapter.find_start_index("https://www.tianyabooks.com/net/csx_03/27175.html", chapters) == 1

    ch1 = adapter.crawl_chapter("https://www.tianyabooks.com/net/csx_03/27174.html", log=lambda _: None)
    assert ch1 == {
        "title": "第一卷 非主流从业指南 第01章 问卜中州 公园邂逅",
        "paragraphs": [
            "太行山上太行关，出关百里不见山。",
            "民谚表述的很形象，巍巍太行在这里绵延到了尽头。",
            "旁座的年青一愣，也跟着所指方向看过去了。",
        ],
    }, ch1

    saved = parse_saved_chapter_html(chapter_html.decode("gb18030"), "tianyabooks_ch1.html")
    assert saved == ch1, saved


def main():
    test_adapter_selection_and_catalog()
    test_adapter_chapter_parser()
    test_bgq99_adapter()
    test_shuba69_adapter()
    test_shubaow_adapter()
    test_biquge_tw_adapter()
    test_tianyabooks_adapter()
    test_saved_html_import_and_challenge_detection()
    test_wa01_http_block_stops_for_manual_import()
    test_resume_and_chapter_start()
    test_stream_limit_end_and_errors()
    test_legacy_url_path()
    print("OK: source adapter, WA01 block handling, saved HTML import, and crawler routing tests passed.")


if __name__ == "__main__":
    main()
