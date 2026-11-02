"""Source adapters for novel websites.

The adapter boundary keeps site-specific URL discovery and HTML parsing out of
the legacy crawler. All messages and source comments stay ASCII-only.
"""

from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from hybrid_session import (
    HybridCrawlerSession,
    CrawlBlockedError,
    has_challenge_indicator,
)


UUKANSHU_HOSTS = {"uukanshu.cc", "www.uukanshu.cc"}
BGQ99_HOSTS = {"bgq99.cc", "www.bgq99.cc", "m.bgq99.cc"}
SHUBA69_HOSTS = {"69shuba.com", "www.69shuba.com", "69shuba.cx", "www.69shuba.cx"}
SHUBAOW_HOSTS = {"shubaow.net", "www.shubaow.net", "m.shubaow.net"}
BIQUGE_TW_HOSTS = {"biquge.tw", "www.biquge.tw", "m.biquge.tw"}
TIANYABOOKS_HOSTS = {"tianyabooks.com", "www.tianyabooks.com", "m.tianyabooks.com", "wx.tianyabooks.com"}
UUKANSHU_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_BGQ99_PROMO_TRAILING_RE = re.compile(
    r"(?:(?:\u8bf7\u8bb0\u4f4f\u672c\u4e66\u9996\u53d1\u57df\u540d|\u9876\u70b9\u5c0f\u8bf4\u7f51\u624b\u673a\u7248\u66f4\u65b0\u6700\u5feb\u7f51\u5740).*$"
    r"|(?:\(\u672c\u7ae0\u5b8c\)|\uff08\u672c\u7ae0\u5b8c\uff09)\s*$)",
    re.IGNORECASE,
)
_CHAPTER_PAGE_SUFFIX_RE = re.compile(r"\s*[\uff08(]\s*\d+\s*/\s*\d+\s*[\uff09)]\s*$")


def _clean_text(value: str) -> str:
    cleaned = _BGQ99_PROMO_TRAILING_RE.sub("", value or "")
    return " ".join(cleaned.split()).strip()


def _clean_chapter_title(value: str) -> str:
    return _CHAPTER_PAGE_SUFFIX_RE.sub("", _clean_text(value)).strip()


def _is_ad_text(value: str) -> bool:
    compact = re.sub(r"\s+", "", value).lower()
    if re.fullmatch(r"loadadv\([^)]*\);?", compact):
        return True
    if compact in ("(\u672c\u7ae0\u5b8c)", "\uff08\u672c\u7ae0\u5b8c\uff09", "()", "\uff08\uff09"):
        return True
    if "bgq99.cc" in compact or "\u8bf7\u8bb0\u4f4f\u672c\u4e66\u9996\u53d1\u57df\u540d" in compact:
        return True
    if "\u8bf7\u7c98\u8d34\u4ee5\u4e0b\u7f51\u5740\u5206\u4eab\u7ed9\u4f60\u7684qq" in compact:
        return True
    return False


def parse_saved_chapter_html(html: str, source_name: str = "saved page") -> dict:
    """Extract one saved wa01 chapter page for offline translation import."""
    if re.search(r"\.(?:mht|mhtml)$", source_name, re.IGNORECASE):
        message = BytesParser(policy=policy.default).parsebytes(html.encode("utf-8"))
        html_parts = [part for part in message.walk() if part.get_content_type() == "text/html"]
        if not html_parts:
            raise ValueError(f"{source_name}: file MHTML khong chua phan HTML.")
        html = html_parts[0].get_content()

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True).lower()
    if has_challenge_indicator(html) or has_challenge_indicator(page_text):
        raise ValueError(
            f"{source_name}: file nay chi chua trang xac minh, chua co noi dung chuong. "
            "Hay doi trang tai xong trong trinh duyet roi luu lai."
        )

    title_node = (soup.select_one("div.title") or soup.select_one("h1")
                  or soup.select_one(".chapter-title"))
    title = _clean_chapter_title(title_node.get_text(" ", strip=True)) if title_node else ""
    book_info_link = soup.select_one("div.book-content div.info a")
    if book_info_link and title:
        book_name = _clean_text(book_info_link.get_text(" ", strip=True))
        if book_name and title.startswith(f"{book_name} "):
            title = title[len(book_name):].strip()
    if not title:
        title = _clean_chapter_title(soup.title.get_text(" ", strip=True)) if soup.title else ""
    if not title:
        title = source_name.rsplit(".", 1)[0]

    content_node = (soup.select_one("div.showtxt#content") or soup.select_one("div.showtxt")
                    or soup.select_one("div#neirong") or soup.select_one("div.neirong")
                    or soup.select_one("div#chaptercontent") or soup.select_one("div.read-content")
                    or soup.select_one("div#htmlContent") or soup.select_one("div.read-content-body")
                    or soup.select_one("div.txtnav") or soup.select_one("div.readcotent")
                    or soup.select_one("div.content") or soup.select_one("#content")
                    or soup.select_one(".chapter-content") or soup.select_one("article"))
    if not content_node:
        raise ValueError(
            f"{source_name}: khong tim thay vung noi dung chuong trong HTML. "
            "Hay chon Save page/Trang web hoan chinh hoac copy noi dung vao file TXT."
        )

    for unwanted in content_node.select(
        "script, style, noscript, nav, iframe, .mobadsq, .anchor_bookmark, "
        ".textinfo, .page_chapter, .txtinfo, #txtright, .bottom-ad, .contentadv, h1"
    ):
        unwanted.decompose()
    paragraphs = []
    p_nodes = content_node.select("p")
    use_p_nodes = bool(p_nodes) and not (len(p_nodes) == 1 and p_nodes[0].find("br") is not None)
    if use_p_nodes:
        for node in p_nodes:
            value = _clean_text(node.get_text(" ", strip=True))
            if value and not _is_ad_text(value):
                if not paragraphs and value == title:
                    continue
                paragraphs.append(value)
    else:
        for line in content_node.get_text("\n", strip=True).splitlines():
            value = _clean_text(line)
            if value and not _is_ad_text(value):
                if not paragraphs and value == title:
                    continue
                paragraphs.append(value)
    if not paragraphs or sum(map(len, paragraphs)) < 20:
        raise ValueError(f"{source_name}: vung noi dung chuong rong hoac qua ngan.")

    return {"title": title, "paragraphs": paragraphs}


class UukanshuAdapter:
    """Adapter for uukanshu.cc book indexes and chapter pages."""

    host = "uukanshu.cc"

    def __init__(self, fetcher=None, session=None, timeout: int = 15):
        self._fetcher = fetcher
        if session is not None:
            self.session = session
        elif fetcher is None:
            self.session = HybridCrawlerSession(user_agent=UUKANSHU_USER_AGENT)
        else:
            self.session = requests.Session()
        self.timeout = timeout
        if hasattr(self.session, "headers"):
            self.session.headers.update({"User-Agent": UUKANSHU_USER_AGENT})

    @staticmethod
    def _book_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/book/(\d+)(?:/\d+\.html?)?", path)
        return match.group(1) if match else None

    @staticmethod
    def _chapter_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/book/(\d+)/(\d+)\.html?", path)
        return (match.group(1), match.group(2)) if match else None

    def is_catalog_url(self, url: str) -> bool:
        path = urlsplit(url).path.rstrip("/")
        return bool(re.fullmatch(r"/book/\d+", path))

    def catalog_url(self, url: str) -> str | None:
        book_id = self._book_id(url)
        if not book_id:
            return None
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}/book/{book_id}/"

    def _request(self, url: str):
        if self._fetcher is not None:
            return self._fetcher(url)
        return self.session.get(url, timeout=self.timeout)

    @staticmethod
    def _response_status(response) -> int:
        return int(getattr(response, "status_code", 200))

    @staticmethod
    def _response_content(response):
        content = getattr(response, "content", None)
        if content is not None:
            return content
        return getattr(response, "text", "")

    def _get_soup(self, url: str, log=print):
        try:
            response = self._request(url)
        except CrawlBlockedError as exc:
            log(f"Blocked response from {url}: {exc}")
            return None
        except Exception as exc:
            log(f"Error fetching {url}: {exc}")
            return False

        status = self._response_status(response)
        if status == 404:
            log(f"Returned 404 (Not Found): {url}")
            return None
        if status in (403, 429):
            log(f"Blocked response {status} from {url}. Stop without bypass.")
            return None
        if status >= 500 or status in (408, 409, 425):
            log(f"Temporary HTTP error {status} from {url}.")
            return False
        if status < 200 or status >= 300:
            log(f"Unexpected HTTP status {status} from {url}. Stop.")
            return None

        try:
            return BeautifulSoup(self._response_content(response), "html.parser")
        except Exception as exc:
            log(f"Could not parse HTML from {url}: {exc}")
            return False

    def list_chapters(self, start_url: str, log=print):
        """Return ordered unique chapter dicts from the book catalog."""
        catalog = self.catalog_url(start_url)
        if not catalog:
            log(f"Invalid uukanshu URL: {start_url}")
            return None

        soup = self._get_soup(catalog, log=log)
        if soup is False or soup is None:
            return soup

        container = soup.select_one("#list-chapterAll")
        if not container:
            log(f"Could not find chapter list container for {catalog}.")
            return None

        book_id = self._book_id(catalog)
        chapters = []
        seen = set()
        for link in container.select("a[href]"):
            href = urljoin(catalog, link.get("href", "").strip())
            chapter = self._chapter_id(href)
            if not chapter or chapter[0] != book_id:
                continue
            canonical = f"{urlsplit(catalog).scheme}://{urlsplit(catalog).netloc}/book/{book_id}/{chapter[1]}.html"
            if canonical in seen:
                continue
            title = _clean_text(link.get_text(" ", strip=True))
            if not title:
                continue
            seen.add(canonical)
            chapters.append({"url": canonical, "title": title})

        if not chapters:
            log(f"No chapters found in {catalog}.")
            return None
        log(f"Found {len(chapters)} chapters in {catalog}.")
        return chapters

    get_chapters = list_chapters

    def find_start_index(self, start_url: str, chapters, log=print) -> int:
        """Find the requested chapter, or zero for a catalog URL."""
        requested = self._chapter_id(start_url)
        if not requested:
            return 0
        for index, chapter in enumerate(chapters):
            if self._chapter_id(chapter["url"]) == requested:
                return index
        log(f"Chapter from start URL was not found in catalog: {start_url}")
        return 0

    def crawl_chapter(self, url: str, log=print):
        log(f"Fetching: {url}")
        soup = self._get_soup(url, log=log)
        if soup is False or soup is None:
            return soup

        title_node = soup.select_one("h1.pt10")
        content_nodes = soup.select("div.readcotent")
        if not title_node:
            log(f"Could not find h1.pt10 for {url}. Stop.")
            return None
        if not content_nodes:
            log(f"Could not find div.readcotent for {url}. Stop.")
            return None

        paragraphs = []
        for node in content_nodes:
            for unwanted in node.find_all(["script", "style", "noscript"]):
                unwanted.decompose()
            text_lines = node.get_text("\n", strip=True).splitlines()
            for line in text_lines:
                text = _clean_text(line)
                if text and not _is_ad_text(text):
                    paragraphs.append(text)

        if not paragraphs:
            log(f"Empty chapter content in div.readcotent for {url}. Stop.")
            return None

        return {
            "title": _clean_text(title_node.get_text(" ", strip=True)),
            "paragraphs": paragraphs,
        }

    parse_chapter = crawl_chapter


class Bgq99Adapter(UukanshuAdapter):
    """Adapter for bgq99.cc book indexes and chapter pages."""

    host = "www.bgq99.cc"

    @staticmethod
    def _canonical_base(url: str) -> str:
        parsed = urlsplit(url)
        scheme = parsed.scheme or "https"
        netloc = (parsed.netloc or "www.bgq99.cc").lower()
        if netloc == "m.bgq99.cc":
            netloc = "www.bgq99.cc"
        return f"{scheme}://{netloc}"

    def catalog_url(self, url: str) -> str | None:
        book_id = self._book_id(url)
        if not book_id:
            return None
        return f"{self._canonical_base(url)}/book/{book_id}/"

    def list_chapters(self, start_url: str, log=print):
        """Return ordered unique chapter dicts from the bgq99.cc book catalog."""
        catalog = self.catalog_url(start_url)
        if not catalog:
            log(f"Invalid bgq99 URL: {start_url}")
            return None

        soup = self._get_soup(catalog, log=log)
        if soup is False or soup is None:
            return soup

        dl = soup.select_one("div.listmain dl") or soup.select_one("#list dl") or soup.find("dl")
        if not dl:
            log(f"Could not find chapter list dl for {catalog}.")
            return None

        # If dl contains multiple <dt> headers (e.g. latest chapters followed by full chapter list),
        # prefer the <dd> elements after the last <dt> when present.
        dd_nodes = []
        dts = dl.find_all("dt")
        if dts:
            after_last_dt = []
            for sibling in dts[-1].find_next_siblings():
                if getattr(sibling, "name", None) == "dd":
                    after_last_dt.append(sibling)
            dd_nodes = after_last_dt or dl.find_all("dd")
        else:
            dd_nodes = dl.find_all("dd")

        book_id = self._book_id(catalog)
        base = self._canonical_base(catalog)
        chapters = []
        seen = set()
        for dd in dd_nodes:
            link = dd.find("a", href=True)
            if not link:
                continue
            href = urljoin(catalog, link.get("href", "").strip())
            chapter = self._chapter_id(href)
            if not chapter or chapter[0] != book_id:
                continue
            canonical = f"{base}/book/{book_id}/{chapter[1]}.html"
            if canonical in seen:
                continue
            title = _clean_text(link.get_text(" ", strip=True))
            if not title:
                continue
            seen.add(canonical)
            chapters.append({"url": canonical, "title": title})

        if not chapters:
            log(f"No chapters found in {catalog}.")
            return None
        log(f"Found {len(chapters)} chapters in {catalog}.")
        return chapters

    get_chapters = list_chapters

    def crawl_chapter(self, url: str, log=print):
        chapter_ref = self._chapter_id(url)
        if chapter_ref:
            url = f"{self._canonical_base(url)}/book/{chapter_ref[0]}/{chapter_ref[1]}.html"
        log(f"Fetching: {url}")
        soup = self._get_soup(url, log=log)
        if soup is False or soup is None:
            return soup

        title_node = (
            soup.select_one("div.content > h1")
            or soup.select_one("div.book.reader h1")
            or soup.select_one("h1")
        )
        content_node = (
            soup.select_one("div#content.showtxt")
            or soup.select_one("div#content")
            or soup.select_one("div.showtxt")
        )
        if not title_node:
            log(f"Could not find chapter h1 for {url}. Stop.")
            return None
        if not content_node:
            log(f"Could not find div#content.showtxt for {url}. Stop.")
            return None

        for unwanted in content_node.select("script, style, noscript, .textinfo, .page_chapter"):
            unwanted.decompose()

        title = _clean_text(title_node.get_text(" ", strip=True))
        paragraphs = []
        for line in content_node.get_text("\n", strip=True).splitlines():
            text = _clean_text(line)
            if not text or _is_ad_text(text):
                continue
            if not paragraphs and text == title:
                continue
            paragraphs.append(text)

        if not paragraphs:
            log(f"Empty chapter content in div#content.showtxt for {url}. Stop.")
            return None

        return {
            "title": title,
            "paragraphs": paragraphs,
        }

    parse_chapter = crawl_chapter


class Shuba69Adapter(UukanshuAdapter):
    """Adapter for 69shuba.com book summary/catalog pages and chapter pages."""

    host = "www.69shuba.com"

    @staticmethod
    def _book_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/(?:book/(\d+)(?:\.html?)?|txt/(\d+)/\d+(?:\.html?)?)", path)
        if not match:
            return None
        return match.group(1) or match.group(2)

    @staticmethod
    def _chapter_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/txt/(\d+)/(\d+)(?:\.html?)?", path)
        return (match.group(1), match.group(2)) if match else None

    def is_catalog_url(self, url: str) -> bool:
        path = urlsplit(url).path.rstrip("/")
        return bool(re.fullmatch(r"/book/\d+(?:\.html?)?", path))

    @staticmethod
    def _canonical_base(url: str) -> str:
        parsed = urlsplit(url)
        scheme = parsed.scheme or "https"
        netloc = (parsed.netloc or "www.69shuba.com").lower()
        if netloc == "69shuba.com":
            netloc = "www.69shuba.com"
        elif netloc == "69shuba.cx":
            netloc = "www.69shuba.cx"
        return f"{scheme}://{netloc}"

    def catalog_url(self, url: str) -> str | None:
        book_id = self._book_id(url)
        if not book_id:
            return None
        return f"{self._canonical_base(url)}/book/{book_id}/"

    @staticmethod
    def _response_content(response):
        content = getattr(response, "content", None)
        if isinstance(content, (bytes, bytearray)):
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                return content.decode("gb18030", errors="replace")
        if content is not None:
            return content
        return getattr(response, "text", "")

    def _request_with_headers(self, url: str, headers: dict | None = None):
        if self._fetcher is not None:
            return self._fetcher(url)
        if headers:
            try:
                return self.session.get(url, headers=headers, timeout=self.timeout)
            except TypeError:
                return self.session.get(url, timeout=self.timeout)
        return self.session.get(url, timeout=self.timeout)

    def _get_soup(self, url: str, log=print, headers: dict | None = None):
        try:
            response = self._request_with_headers(url, headers=headers)
        except CrawlBlockedError as exc:
            log(f"Blocked response from {url}: {exc}")
            return None
        except Exception as exc:
            log(f"Error fetching {url}: {exc}")
            return False

        status = self._response_status(response)
        if status == 404:
            log(f"Returned 404 (Not Found): {url}")
            return None
        if status in (403, 429):
            log(f"Blocked response {status} from {url}. Stop without bypass.")
            return None
        if status >= 500 or status in (408, 409, 425):
            log(f"Temporary HTTP error {status} from {url}.")
            return False
        if status < 200 or status >= 300:
            log(f"Unexpected HTTP status {status} from {url}. Stop.")
            return None

        try:
            return BeautifulSoup(self._response_content(response), "html.parser")
        except Exception as exc:
            log(f"Could not parse HTML from {url}: {exc}")
            return False

    def list_chapters(self, start_url: str, log=print):
        """Return ordered unique chapter dicts from the 69shuba.com book catalog."""
        catalog = self.catalog_url(start_url)
        if not catalog:
            log(f"Invalid 69shuba URL: {start_url}")
            return None

        book_id = self._book_id(catalog)
        base = self._canonical_base(catalog)
        referer = f"{base}/book/{book_id}.htm"
        soup = self._get_soup(catalog, log=log, headers={"Referer": referer})
        if soup is False or soup is None:
            return soup

        container = soup.select_one("div#catalog") or soup.select_one("#catalog")
        if not container:
            log(f"Could not find div#catalog for {catalog}.")
            return None

        raw_items = []
        for idx, li in enumerate(container.select("ul li")):
            link = li.find("a", href=True)
            if not link:
                continue
            href = urljoin(catalog, link.get("href", "").strip())
            chapter = self._chapter_id(href)
            if not chapter or chapter[0] != book_id:
                continue
            canonical = f"{base}/txt/{book_id}/{chapter[1]}"
            title = _clean_text(link.get_text(" ", strip=True))
            if not title:
                continue
            data_num = li.get("data-num", "")
            try:
                num_key = int(str(data_num).strip())
            except ValueError:
                num_key = None
            raw_items.append((num_key, idx, {"url": canonical, "title": title}))

        if not raw_items:
            log(f"No chapters found in {catalog}.")
            return None

        # 69shuba lists chapters in reverse order (descending data-num) inside #catalog by default.
        if all(item[0] is not None for item in raw_items):
            raw_items.sort(key=lambda item: (item[0], item[1]))
        elif len(raw_items) >= 2 and raw_items[0][0] is not None and raw_items[-1][0] is not None:
            if raw_items[0][0] > raw_items[-1][0]:
                raw_items.reverse()

        chapters = []
        seen = set()
        for _, _, entry in raw_items:
            if entry["url"] in seen:
                continue
            seen.add(entry["url"])
            chapters.append(entry)

        log(f"Found {len(chapters)} chapters in {catalog}.")
        return chapters

    get_chapters = list_chapters

    def crawl_chapter(self, url: str, log=print):
        chapter_ref = self._chapter_id(url)
        if not chapter_ref:
            log(f"Invalid 69shuba chapter URL: {url}")
            return None
        base = self._canonical_base(url)
        book_id, chapter_id = chapter_ref
        canonical_url = f"{base}/txt/{book_id}/{chapter_id}"
        referer = f"{base}/book/{book_id}/"
        log(f"Fetching: {canonical_url}")
        soup = self._get_soup(canonical_url, log=log, headers={"Referer": referer})
        if soup is False or soup is None:
            return soup

        content_node = soup.select_one("div.txtnav") or soup.select_one("#txtnav")
        if not content_node:
            log(f"Could not find div.txtnav for {canonical_url}. Stop.")
            return None

        title_node = content_node.select_one("h1") or soup.select_one("h1")
        if not title_node:
            log(f"Could not find chapter h1 for {canonical_url}. Stop.")
            return None
        title = _clean_text(title_node.get_text(" ", strip=True))

        for unwanted in content_node.select(
            "h1, .txtinfo, #txtright, .bottom-ad, .contentadv, script, style, noscript, iframe, nav"
        ):
            unwanted.decompose()

        paragraphs = []
        for line in content_node.get_text("\n", strip=True).splitlines():
            text = _clean_text(line)
            if not text or _is_ad_text(text):
                continue
            if not paragraphs and text == title:
                continue
            paragraphs.append(text)

        if not paragraphs:
            log(f"Empty chapter content in div.txtnav for {canonical_url}. Stop.")
            return None

        return {
            "title": title,
            "paragraphs": paragraphs,
        }

    parse_chapter = crawl_chapter


class ShubaowAdapter(Shuba69Adapter):
    """Adapter for shubaow.net book catalog pages (/book/<id>.html) and chapter pages."""

    host = "www.shubaow.net"

    @staticmethod
    def _book_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/book/(\d+)(?:\.html?|/\d+\.html?)?", path)
        return match.group(1) if match else None

    @staticmethod
    def _chapter_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/book/(\d+)/(\d+)\.html?", path)
        return (match.group(1), match.group(2)) if match else None

    def is_catalog_url(self, url: str) -> bool:
        path = urlsplit(url).path.rstrip("/")
        return bool(re.fullmatch(r"/book/\d+(?:\.html?)?", path))

    @staticmethod
    def _canonical_base(url: str) -> str:
        parsed = urlsplit(url)
        scheme = parsed.scheme or "https"
        netloc = (parsed.netloc or "www.shubaow.net").lower()
        if netloc in ("shubaow.net", "m.shubaow.net"):
            netloc = "www.shubaow.net"
        return f"{scheme}://{netloc}"

    def catalog_url(self, url: str) -> str | None:
        book_id = self._book_id(url)
        if not book_id:
            return None
        return f"{self._canonical_base(url)}/book/{book_id}.html"

    def list_chapters(self, start_url: str, log=print):
        """Return ordered unique chapter dicts from the shubaow.net book catalog."""
        catalog = self.catalog_url(start_url)
        if not catalog:
            log(f"Invalid shubaow URL: {start_url}")
            return None

        soup = self._get_soup(catalog, log=log)
        if soup is False or soup is None:
            return soup

        container = (
            soup.select_one("div#list-chapterAll")
            or soup.select_one("div.chapter-list-grid")
            or soup.select_one("#list")
        )
        if not container:
            log(f"Could not find chapter list container for {catalog}.")
            return None

        book_id = self._book_id(catalog)
        base = self._canonical_base(catalog)
        chapters = []
        seen = set()
        for link in container.select("a[href]"):
            href = urljoin(catalog, link.get("href", "").strip())
            chapter = self._chapter_id(href)
            if not chapter or chapter[0] != book_id:
                continue
            canonical = f"{base}/book/{book_id}/{chapter[1]}.html"
            if canonical in seen:
                continue
            title = _clean_text(link.get_text(" ", strip=True))
            if not title:
                continue
            seen.add(canonical)
            chapters.append({"url": canonical, "title": title})

        if not chapters:
            log(f"No chapters found in {catalog}.")
            return None
        log(f"Found {len(chapters)} chapters in {catalog}.")
        return chapters

    get_chapters = list_chapters

    def crawl_chapter(self, url: str, log=print):
        chapter_ref = self._chapter_id(url)
        if not chapter_ref:
            log(f"Invalid shubaow chapter URL: {url}")
            return None
        base = self._canonical_base(url)
        book_id, chapter_id = chapter_ref
        canonical_url = f"{base}/book/{book_id}/{chapter_id}.html"
        referer = f"{base}/book/{book_id}.html"
        log(f"Fetching: {canonical_url}")
        soup = self._get_soup(canonical_url, log=log, headers={"Referer": referer})
        if soup is False or soup is None:
            return soup

        title_node = (
            soup.select_one("h1.read-title")
            or soup.select_one("div.read-header h1")
            or soup.select_one("h1")
        )
        content_node = (
            soup.select_one("div#htmlContent")
            or soup.select_one("div.read-content-body")
        )
        if not title_node:
            log(f"Could not find chapter h1 for {canonical_url}. Stop.")
            return None
        if not content_node:
            log(f"Could not find div#htmlContent for {canonical_url}. Stop.")
            return None

        for unwanted in content_node.select(
            "script, style, noscript, .read-header, .read-pager-group, .read-tips-text"
        ):
            unwanted.decompose()

        title = _clean_text(title_node.get_text(" ", strip=True))
        paragraphs = []
        for line in content_node.get_text("\n", strip=True).splitlines():
            text = _clean_text(line)
            if not text or _is_ad_text(text):
                continue
            if not paragraphs and text == title:
                continue
            paragraphs.append(text)

        if not paragraphs:
            log(f"Empty chapter content in div#htmlContent for {canonical_url}. Stop.")
            return None

        return {
            "title": title,
            "paragraphs": paragraphs,
        }

    parse_chapter = crawl_chapter


class BiqugeTwAdapter(Shuba69Adapter):
    """Adapter for biquge.tw book catalog pages (/book/<id>/) and chapter pages."""

    host = "www.biquge.tw"

    @staticmethod
    def _book_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/book/(\d+)(?:\.html?|/\d+(?:_\d+)?\.html?)?", path)
        return match.group(1) if match else None

    @staticmethod
    def _chapter_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(r"/book/(\d+)/(\d+)(?:_\d+)?\.html?", path)
        return (match.group(1), match.group(2)) if match else None

    def is_catalog_url(self, url: str) -> bool:
        path = urlsplit(url).path.rstrip("/")
        return bool(re.fullmatch(r"/book/\d+(?:\.html?)?", path))

    @staticmethod
    def _canonical_base(url: str) -> str:
        parsed = urlsplit(url)
        scheme = parsed.scheme or "https"
        netloc = (parsed.netloc or "www.biquge.tw").lower()
        if netloc in ("biquge.tw", "m.biquge.tw"):
            netloc = "www.biquge.tw"
        return f"{scheme}://{netloc}"

    def catalog_url(self, url: str) -> str | None:
        book_id = self._book_id(url)
        if not book_id:
            return None
        return f"{self._canonical_base(url)}/book/{book_id}/"

    def list_chapters(self, start_url: str, log=print):
        """Return ordered unique chapter dicts from the biquge.tw book catalog."""
        catalog = self.catalog_url(start_url)
        if not catalog:
            log(f"Invalid biquge.tw URL: {start_url}")
            return None

        soup = self._get_soup(catalog, log=log)
        if soup is False or soup is None:
            return soup

        container = (
            soup.select_one("div.list-chapter")
            or soup.select_one("div.booklist")
            or soup.select_one("#list")
        )
        if not container:
            log(f"Could not find chapter list container for {catalog}.")
            return None

        book_id = self._book_id(catalog)
        base = self._canonical_base(catalog)
        chapters = []
        seen = set()
        for link in container.select("a[href]"):
            href = urljoin(catalog, link.get("href", "").strip())
            chapter = self._chapter_id(href)
            if not chapter or chapter[0] != book_id:
                continue
            canonical = f"{base}/book/{book_id}/{chapter[1]}.html"
            if canonical in seen:
                continue
            title = _clean_chapter_title(link.get_text(" ", strip=True))
            if not title:
                continue
            seen.add(canonical)
            chapters.append({"url": canonical, "title": title})

        if not chapters:
            log(f"No chapters found in {catalog}.")
            return None
        log(f"Found {len(chapters)} chapters in {catalog}.")
        return chapters

    get_chapters = list_chapters

    @staticmethod
    def _extract_paragraphs(content_node, title: str) -> list[str]:
        for unwanted in content_node.select("script, style, noscript, .read-page, h1"):
            unwanted.decompose()
        paragraphs = []
        p_nodes = content_node.select("p")
        if p_nodes:
            for node in p_nodes:
                text = _clean_text(node.get_text(" ", strip=True))
                if not text or _is_ad_text(text):
                    continue
                if not paragraphs and text == title:
                    continue
                paragraphs.append(text)
        else:
            for line in content_node.get_text("\n", strip=True).splitlines():
                text = _clean_text(line)
                if not text or _is_ad_text(text):
                    continue
                if not paragraphs and text == title:
                    continue
                paragraphs.append(text)
        return paragraphs

    def _find_next_page_url(self, soup: BeautifulSoup, current_url: str, book_id: str, chapter_id: str):
        pattern = re.compile(rf"^/book/{re.escape(book_id)}/{re.escape(chapter_id)}_\d+\.html?$")
        for link in soup.select("div.read-page a[href], a[rel='next'][href]"):
            href = urljoin(current_url, link.get("href", "").strip())
            path = urlsplit(href).path.rstrip("/")
            if pattern.fullmatch(path):
                return f"{self._canonical_base(current_url)}{path}"
        return None

    def crawl_chapter(self, url: str, log=print):
        chapter_ref = self._chapter_id(url)
        if not chapter_ref:
            log(f"Invalid biquge.tw chapter URL: {url}")
            return None
        base = self._canonical_base(url)
        book_id, chapter_id = chapter_ref
        canonical_url = f"{base}/book/{book_id}/{chapter_id}.html"
        referer = f"{base}/book/{book_id}/"
        log(f"Fetching: {canonical_url}")

        visited = set()
        current_url = canonical_url
        current_referer = referer
        title = ""
        paragraphs = []

        while current_url and current_url not in visited and len(visited) < 20:
            visited.add(current_url)
            soup = self._get_soup(current_url, log=log, headers={"Referer": current_referer})
            if soup is False or soup is None:
                return soup

            title_node = (
                soup.select_one("div.book.read h1")
                or soup.select_one("h1")
            )
            content_node = (
                soup.select_one("div#chaptercontent")
                or soup.select_one("div.read-content")
            )
            if not title and title_node:
                title = _clean_chapter_title(title_node.get_text(" ", strip=True))
            if not title:
                log(f"Could not find chapter h1 for {current_url}. Stop.")
                return None
            if not content_node:
                log(f"Could not find div#chaptercontent for {current_url}. Stop.")
                return None

            next_url = self._find_next_page_url(soup, current_url, book_id, chapter_id)
            paragraphs.extend(self._extract_paragraphs(content_node, title))
            current_referer = current_url
            current_url = next_url

        if not paragraphs:
            log(f"Empty chapter content in div#chaptercontent for {canonical_url}. Stop.")
            return None

        return {
            "title": title,
            "paragraphs": paragraphs,
        }

    parse_chapter = crawl_chapter


class TianyaBooksAdapter(Shuba69Adapter):
    """Adapter for tianyabooks.com book catalog pages (/<cat>/<slug>/) and chapter pages."""

    host = "www.tianyabooks.com"

    @staticmethod
    def _book_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(
            r"/([a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)?)(?:/index\.html?|/\d+\.html?)?",
            path,
        )
        if not match:
            return None
        book_path = match.group(1)
        if book_path.lower().endswith((".html", ".htm")):
            return None
        return book_path

    @staticmethod
    def _chapter_id(url: str):
        path = urlsplit(url).path.rstrip("/")
        match = re.fullmatch(
            r"/([a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)?)/(\d+)\.html?",
            path,
        )
        return (match.group(1), match.group(2)) if match else None

    def is_catalog_url(self, url: str) -> bool:
        return bool(self._book_id(url)) and self._chapter_id(url) is None

    @staticmethod
    def _canonical_base(url: str) -> str:
        parsed = urlsplit(url)
        scheme = parsed.scheme or "https"
        netloc = (parsed.netloc or "www.tianyabooks.com").lower()
        if netloc in ("tianyabooks.com", "m.tianyabooks.com"):
            netloc = "www.tianyabooks.com"
        return f"{scheme}://{netloc}"

    def catalog_url(self, url: str) -> str | None:
        book_id = self._book_id(url)
        if not book_id:
            return None
        return f"{self._canonical_base(url)}/{book_id}/"

    def list_chapters(self, start_url: str, log=print):
        """Return ordered unique chapter dicts from the tianyabooks.com book catalog."""
        catalog = self.catalog_url(start_url)
        if not catalog:
            log(f"Invalid tianyabooks URL: {start_url}")
            return None

        soup = self._get_soup(catalog, log=log)
        if soup is False or soup is None:
            return soup

        mulu_lists = (
            soup.select("div.catalog div.mulu-list")
            or soup.select("div.mulu-list")
        )
        if not mulu_lists:
            log(f"Could not find div.mulu-list container for {catalog}.")
            return None

        book_id = self._book_id(catalog)
        base = self._canonical_base(catalog)
        chapters = []
        seen = set()
        for block in mulu_lists:
            for link in block.select("a[href]"):
                href = urljoin(catalog, link.get("href", "").strip())
                chapter = self._chapter_id(href)
                if not chapter or chapter[0] != book_id:
                    continue
                canonical = f"{base}/{book_id}/{chapter[1]}.html"
                if canonical in seen:
                    continue
                title = _clean_chapter_title(link.get_text(" ", strip=True))
                if not title:
                    continue
                seen.add(canonical)
                chapters.append({"url": canonical, "title": title})

        if not chapters:
            log(f"No chapters found in {catalog}.")
            return None
        log(f"Found {len(chapters)} chapters in {catalog}.")
        return chapters

    get_chapters = list_chapters

    def crawl_chapter(self, url: str, log=print):
        chapter_ref = self._chapter_id(url)
        if not chapter_ref:
            log(f"Invalid tianyabooks chapter URL: {url}")
            return None
        base = self._canonical_base(url)
        book_id, chapter_id = chapter_ref
        canonical_url = f"{base}/{book_id}/{chapter_id}.html"
        referer = f"{base}/{book_id}/"
        log(f"Fetching: {canonical_url}")

        soup = self._get_soup(canonical_url, log=log, headers={"Referer": referer})
        if soup is False or soup is None:
            return soup

        title_node = (
            soup.select_one("div.book-content h1")
            or soup.select_one("h1")
        )
        content_node = (
            soup.select_one("div#neirong")
            or soup.select_one("div.neirong")
        )
        if not title_node:
            log(f"Could not find chapter h1 for {canonical_url}. Stop.")
            return None
        if not content_node:
            log(f"Could not find div#neirong for {canonical_url}. Stop.")
            return None

        title = _clean_chapter_title(title_node.get_text(" ", strip=True))
        book_info_link = soup.select_one("div.book-content div.info a")
        if book_info_link and title:
            book_name = _clean_text(book_info_link.get_text(" ", strip=True))
            if book_name and title.startswith(f"{book_name} "):
                title = title[len(book_name):].strip()

        for unwanted in content_node.select("script, style, noscript, h1"):
            unwanted.decompose()

        paragraphs = []
        for line in content_node.get_text("\n", strip=True).splitlines():
            text = _clean_text(line)
            if not text or _is_ad_text(text):
                continue
            if not paragraphs and text == title:
                continue
            paragraphs.append(text)

        if not paragraphs:
            log(f"Empty chapter content in div#neirong for {canonical_url}. Stop.")
            return None

        return {
            "title": title,
            "paragraphs": paragraphs,
        }

    parse_chapter = crawl_chapter


def find_adapter(url: str):
    """Return a domain adapter, or None for the legacy crawler path."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    if host in UUKANSHU_HOSTS:
        return UukanshuAdapter()
    if host in BGQ99_HOSTS:
        return Bgq99Adapter()
    if host in SHUBA69_HOSTS:
        return Shuba69Adapter()
    if host in SHUBAOW_HOSTS:
        return ShubaowAdapter()
    if host in BIQUGE_TW_HOSTS:
        return BiqugeTwAdapter()
    if host in TIANYABOOKS_HOSTS:
        return TianyaBooksAdapter()
    return None
