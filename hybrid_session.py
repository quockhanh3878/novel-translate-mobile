"""Hybrid Crawler Session combining Fast TLS Impersonation (curl_cffi)
and Headless Browser Fallback (Playwright Stealth).

Designed for novel-translate-mobile to support both Desktop and Termux.
"""

from __future__ import annotations

import importlib
import os
import random
import time
from typing import Callable, Optional

# Detection flags for optional dependencies (loaded via importlib to avoid static missing-import warnings)
try:
    cffi_requests = importlib.import_module("curl_cffi.requests")
    HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    HAS_CURL_CFFI = False

try:
    cloudscraper = importlib.import_module("cloudscraper")
    HAS_CLOUDSCRAPER = True
except ImportError:
    cloudscraper = None
    HAS_CLOUDSCRAPER = False

try:
    _pw_sync = importlib.import_module("playwright.sync_api")
    sync_playwright = getattr(_pw_sync, "sync_playwright", None)
    try:
        _pw_stealth = importlib.import_module("playwright_stealth")
        stealth_sync = getattr(_pw_stealth, "stealth_sync", None)
    except ImportError:
        stealth_sync = None
    HAS_PLAYWRIGHT = sync_playwright is not None
except ImportError:
    sync_playwright = None
    stealth_sync = None
    HAS_PLAYWRIGHT = False


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CHALLENGE_INDICATORS = (
    "/__gatekeeper_challenge/",
    "challenge_required",
    "browser verification required",
    "cf-turnstile",
    "checking your browser",
    "just a moment...",
)


class CrawlBlockedError(RuntimeError):
    """Raised when website blocks crawling and automated bypass cannot resolve it."""
    pass


def has_challenge_indicator(html_text: str) -> bool:
    """Return True if the HTML text contains known bot-verification indicators."""
    if not html_text:
        return False
    lower_text = html_text.lower()
    return any(indicator in lower_text for indicator in CHALLENGE_INDICATORS)


def is_challenge_response(status_code: int, html_text: str) -> bool:
    """Check if the HTTP response indicates a bot challenge or verification wall."""
    if status_code in (403, 429):
        return True
    return has_challenge_indicator(html_text)


class HybridCrawlerSession:
    """Manages HTTP requests with TLS impersonation, cookie persistence, and browser fallback."""

    def __init__(
        self,
        impersonate: str = "chrome120",
        user_agent: str = DEFAULT_USER_AGENT,
        enable_browser_fallback: bool = True,
        log: Callable = print,
    ):
        self.impersonate = impersonate
        self.user_agent = user_agent
        self.enable_browser_fallback = enable_browser_fallback
        self.log = log
        self._session = None
        self._init_session()

    def _init_session(self):
        """Initialize the fast HTTP session (prefer curl_cffi, fallback to cloudscraper)."""
        if HAS_CURL_CFFI and cffi_requests is not None:
            self._session = cffi_requests.Session(impersonate=self.impersonate)
            self._session.headers.update({"User-Agent": self.user_agent})
            self.engine = "curl_cffi"
        elif HAS_CLOUDSCRAPER and cloudscraper is not None:
            self._session = cloudscraper.create_scraper()
            self._session.headers.update({"User-Agent": self.user_agent})
            self.engine = "cloudscraper"
        else:
            import requests
            self._session = requests.Session()
            self._session.headers.update({"User-Agent": self.user_agent})
            self.engine = "requests"

    def get(self, url: str, headers: Optional[dict] = None, timeout: int = 15, retries: int = 2):
        """Execute HTTP GET with automatic challenge detection and fallback."""
        merged_headers = {"User-Agent": self.user_agent}
        if headers:
            merged_headers.update(headers)

        current_delay = 2.0
        for attempt in range(retries + 1):
            try:
                response = self._session.get(url, headers=merged_headers, timeout=timeout)
                status_code = getattr(response, "status_code", 200)
                text = getattr(response, "text", "")

                # Pure rate limiting (HTTP 429 without challenge wall) uses exponential backoff first
                if status_code == 429 and not has_challenge_indicator(text) and attempt < retries:
                    self.log(f"HTTP 429 (Rate limit) from {url}. Backoff {current_delay:.1f}s...")
                    time.sleep(current_delay)
                    current_delay *= 2
                    continue

                if is_challenge_response(status_code, text):
                    self.log(f"Phat hien co che chan bot ({status_code}) tai {url}.")
                    if self.enable_browser_fallback and HAS_PLAYWRIGHT:
                        solved = self._harvest_and_sync_cookies(url)
                        if solved:
                            self.log("Giai ma thanh cong qua Headless Browser, thu lai request...")
                            merged_headers["User-Agent"] = self.user_agent
                            response = self._session.get(url, headers=merged_headers, timeout=timeout)
                            status_code = getattr(response, "status_code", 200)
                            text = getattr(response, "text", "")
                            if not is_challenge_response(status_code, text):
                                return response

                    raise CrawlBlockedError(
                        f"Nguon yeu cau xac minh bang trinh duyet (HTTP {status_code}): {url}. "
                        "Hay mo trang bang trinh duyet, luu trang chuong thanh HTML va "
                        "nhap file HTML vao giao dien de tiep tuc dich."
                    )

                return response

            except CrawlBlockedError:
                raise
            except Exception as exc:
                if attempt < retries:
                    self.log(f"Loi ket noi {url}: {exc}. Thu lai sau {current_delay:.1f}s...")
                    time.sleep(current_delay)
                    current_delay *= 2
                else:
                    raise exc

    def _harvest_and_sync_cookies(self, url: str) -> bool:
        """Run headless browser to solve challenge and synchronize cookies back to fast session."""
        if sync_playwright is None:
            return False
        self.log("Dang khoi dong Headless Browser de giai ma xac minh...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(user_agent=self.user_agent)
                page = context.new_page()
                if stealth_sync:
                    stealth_sync(page)

                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                cookies = []
                # Wait for challenge clearance (up to 12s)
                for step in range(12):
                    page_content = page.content()
                    cookies = context.cookies()
                    has_clearance = any(c.get("name") == "cf_clearance" for c in cookies)
                    still_challenged = has_challenge_indicator(page_content)
                    if has_clearance and not still_challenged:
                        break
                    if not still_challenged and step >= 1:
                        break
                    time.sleep(1.0)

                if not cookies:
                    cookies = context.cookies()
                browser.close()

                if cookies:
                    for cookie in cookies:
                        self.set_cookie(cookie["name"], cookie["value"], domain=cookie.get("domain"))
                    self.log(f"Da dong bo {len(cookies)} cookies vao HTTP session.")
                    return True

        except Exception as exc:
            self.log(f"Khong the giai ma bang Headless Browser: {exc}")

        return False

    def set_cookie(self, name: str, value: str, domain: Optional[str] = None):
        """Set cookie into active fast session."""
        if hasattr(self._session, "cookies"):
            if domain:
                self._session.cookies.set(name, value, domain=domain)
            else:
                self._session.cookies.set(name, value)

    def get_cookie(self, name: str, domain: Optional[str] = None) -> Optional[str]:
        """Retrieve a cookie value by name across curl_cffi, cloudscraper, and requests sessions."""
        cookies_obj = getattr(self._session, "cookies", None)
        if cookies_obj is None:
            return None
        try:
            if domain:
                val = cookies_obj.get(name, domain=domain)
                if val is not None:
                    return val
            return cookies_obj.get(name)
        except TypeError:
            return dict(cookies_obj).get(name)

    def get_cookies_dict(self) -> dict[str, str]:
        """Return all session cookies as a plain {name: value} dictionary."""
        cookies_obj = getattr(self._session, "cookies", None)
        if cookies_obj is None:
            return {}
        return dict(cookies_obj)
