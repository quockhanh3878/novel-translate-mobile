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
UUKANSHU_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _is_ad_text(value: str) -> bool:
    compact = re.sub(r"\s+", "", value).lower()
    return bool(re.fullmatch(r"loadadv\([^)]*\);?", compact))


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
    content_node = (soup.select_one("div.content") or soup.select_one("#content")
                    or soup.select_one(".chapter-content") or soup.select_one("article"))
    if not content_node:
        raise ValueError(
            f"{source_name}: khong tim thay vung noi dung chuong trong HTML. "
            "Hay chon Save page/Trang web hoan chinh hoac copy noi dung vao file TXT."
        )

    for unwanted in content_node.select("script, style, noscript, nav, iframe, .mobadsq, .anchor_bookmark"):
        unwanted.decompose()
    paragraphs = []
    nodes = content_node.select("p") or [content_node]
    for node in nodes:
        value = _clean_text(node.get_text(" ", strip=True))
        if value and not _is_ad_text(value):
            paragraphs.append(value)
    if not paragraphs or sum(map(len, paragraphs)) < 20:
        raise ValueError(f"{source_name}: vung noi dung chuong rong hoac qua ngan.")

    title = _clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
    if not title:
        title = _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    if not title:
        title = source_name.rsplit(".", 1)[0]
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


def find_adapter(url: str):
    """Return a domain adapter, or None for the legacy crawler path."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    if host in UUKANSHU_HOSTS:
        return UukanshuAdapter()
    return None
