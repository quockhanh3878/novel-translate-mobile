"""Hybrid Crawler Session combining Fast TLS Impersonation (curl_cffi)
and Headless Browser Fallback (Playwright Stealth).

Designed for novel-translate-mobile to support both Desktop and Termux.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import random
import re
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import time
import urllib.request
from typing import Callable, Optional
from urllib.parse import urljoin, urlsplit

# Detection flags for optional dependencies (loaded via importlib to avoid static missing-import warnings)
try:
    cffi_requests = importlib.import_module("curl_cffi.requests")
    _cffi_mod = importlib.import_module("curl_cffi")
    CURL_HTTP_V3 = getattr(getattr(_cffi_mod, "CurlHttpVersion", None), "V3", None)
    HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    CURL_HTTP_V3 = None
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


_GK_CHALLENGE_ID_RE = re.compile(r'challengeId\s*:\s*"([^"]+)"')
_GK_TICKET_RE = re.compile(r'ticket\s*:\s*"([^"]+)"')
_GK_VERIFY_URL_RE = re.compile(r'verifyUrl\s*:\s*"([^"]+)"')
_GK_DIFFICULTY_RE = re.compile(r'difficultyBits\s*:\s*(\d+)')


def parse_gatekeeper_challenge(html_text: str) -> Optional[dict]:
    """Extract Gatekeeper Proof-of-Work challenge config from a 403 HTML page."""
    if not html_text or "gatekeeperChallenge" not in html_text:
        return None
    cid_m = _GK_CHALLENGE_ID_RE.search(html_text)
    ticket_m = _GK_TICKET_RE.search(html_text)
    if not cid_m or not ticket_m:
        return None
    verify_m = _GK_VERIFY_URL_RE.search(html_text)
    diff_m = _GK_DIFFICULTY_RE.search(html_text)
    difficulty = int(diff_m.group(1)) if diff_m else 12
    return {
        "challenge_id": cid_m.group(1),
        "ticket": ticket_m.group(1),
        "verify_url": verify_m.group(1) if verify_m else "/__gatekeeper_challenge/verify",
        "difficulty_bits": max(1, min(difficulty, 24)),
    }


def _leading_zero_bits(digest: bytes) -> int:
    n = 0
    for b in digest:
        if b == 0:
            n += 8
        else:
            n += 8 - b.bit_length()
            break
    return n


def solve_gatekeeper_pow(
    challenge_id: str,
    difficulty_bits: int,
    max_iterations: int = 2_000_000,
) -> Optional[str]:
    """Find a decimal nonce where SHA256('gatekeeper-pow-v1:' + challenge_id + ':' + nonce)
    starts with at least `difficulty_bits` zero bits."""
    prefix = f"gatekeeper-pow-v1:{challenge_id}:".encode("utf-8")
    for nonce in range(max_iterations):
        digest = hashlib.sha256(prefix + str(nonce).encode("ascii")).digest()
        if _leading_zero_bits(digest) >= difficulty_bits:
            return str(nonce)
    return None


_DOMAIN_CLEARANCE_CACHE: dict[str, dict] = {}


def _base_domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        return host[4:]
    if host.startswith("m."):
        return host[2:]
    return host


def _find_system_chromium_binary() -> Optional[str]:
    candidates = [
        os.environ.get("CHROME_BIN", ""),
        "/data/data/com.termux/files/usr/bin/chromium",
        "/data/data/com.termux/files/usr/bin/chromium-browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        shutil.which("msedge") or "",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _is_headless_environment() -> bool:
    if os.path.exists("/data/data/com.termux") or "com.termux" in os.environ.get("PREFIX", ""):
        return True
    if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def _build_cdp_browser_args(
    browser_bin: str, user_data_dir: str, port: int, url: str, user_agent: str
) -> list[str]:
    clean_ua = (user_agent or DEFAULT_USER_AGENT).replace("HeadlessChrome/", "Chrome/")
    base = [
        browser_bin,
        f"--user-data-dir={user_data_dir}",
        f"--remote-debugging-port={port}",
        "--window-size=1280,800",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if _is_headless_environment():
        base.extend([
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--user-agent={clean_ua}",
        ])
    else:
        base.append("--window-position=-32000,-32000")
    base.append(url)
    return base


class _SimpleHTTPResponse:
    """Minimal requests-compatible response object for stdlib HTTP/2 and CDP fallbacks."""

    def __init__(self, status_code: int, content: bytes, text: Optional[str] = None):
        self.status_code = status_code
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _encode_hpack_literal(name: str, value: str) -> bytes:
    nb = name.lower().encode("ascii")
    vb = value.encode("latin1", errors="ignore")

    def enc_int(n: int) -> bytes:
        if n < 127:
            return bytes([n])
        out = bytearray([127])
        n -= 127
        while n >= 128:
            out.append((n & 0x7F) | 0x80)
            n >>= 7
        out.append(n)
        return bytes(out)

    return b"\x00" + enc_int(len(nb)) + nb + enc_int(len(vb)) + vb


def _cdp_ws_call(ws_url: str, method: str, params: Optional[dict] = None, timeout: float = 10.0) -> dict:
    rest = ws_url.split("://", 1)[1]
    host_port, path = rest.split("/", 1)
    host, port = host_port.split(":")
    path = "/" + path
    sock = socket.create_connection((host, int(port)), timeout=timeout)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise EOFError("WebSocket handshake closed unexpectedly")
            buf += chunk
        payload = json.dumps({"id": 1, "method": method, "params": params or {}}).encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", 0x81, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, length)
        sock.sendall(header + mask + masked)
        rem = buf.split(b"\r\n\r\n", 1)[1]

        def read_exact(n: int) -> bytes:
            nonlocal rem
            while len(rem) < n:
                chunk = sock.recv(65536)
                if not chunk:
                    raise EOFError("WebSocket frame truncated")
                rem += chunk
            out, rem = rem[:n], rem[n:]
            return out

        while True:
            b1, b2 = struct.unpack("!BB", read_exact(2))
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack("!H", read_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack("!Q", read_exact(8))[0]
            if b2 & 0x80:
                m = read_exact(4)
                data = bytes(b ^ m[i % 4] for i, b in enumerate(read_exact(ln)))
            else:
                data = read_exact(ln)
            if (b1 & 0x0F) == 1:
                msg = json.loads(data.decode("utf-8"))
                if msg.get("id") == 1:
                    return msg.get("result", {})
    finally:
        sock.close()


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
        self._prefer_http3 = False
        self._prefer_stdlib_h2 = False
        self._last_cdp_response: Optional[_SimpleHTTPResponse] = None
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
            self._session.headers.update({
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            self.engine = "requests"

    def _apply_cached_clearance(self, url: str):
        domain = _base_domain(url)
        cached = _DOMAIN_CLEARANCE_CACHE.get(domain)
        if not cached:
            return
        ua = cached.get("user_agent")
        if ua:
            self.user_agent = ua
            if hasattr(self._session, "headers"):
                self._session.headers.update({"User-Agent": ua})
        for cookie in cached.get("cookies", []):
            self.set_cookie(cookie["name"], cookie["value"], domain=cookie.get("domain"))

    def get(self, url: str, headers: Optional[dict] = None, timeout: int = 15, retries: int = 2):
        """Execute HTTP GET with automatic challenge detection and fallback."""
        self._apply_cached_clearance(url)
        merged_headers = {"User-Agent": self.user_agent}
        if headers:
            merged_headers.update(headers)
            if "User-Agent" in headers and _base_domain(url) in _DOMAIN_CLEARANCE_CACHE:
                merged_headers["User-Agent"] = self.user_agent

        current_delay = 2.0
        for attempt in range(retries + 1):
            try:
                if self._prefer_stdlib_h2 and "get" not in getattr(self._session, "__dict__", {}):
                    h2_direct = self._try_stdlib_h2_request(url, merged_headers, timeout)
                    if h2_direct is not None:
                        return h2_direct

                if (
                    self._prefer_http3
                    and CURL_HTTP_V3 is not None
                    and cffi_requests is not None
                    and isinstance(self._session, cffi_requests.Session)
                ):
                    response = self._session.get(
                        url, headers=merged_headers, timeout=timeout, http_version=CURL_HTTP_V3
                    )
                else:
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
                    if self._solve_gatekeeper_challenge(url, text, merged_headers, timeout):
                        self.log("Da giai ma Gatekeeper PoW thanh cong, thu lai request...")
                        response = self._session.get(url, headers=merged_headers, timeout=timeout)
                        status_code = getattr(response, "status_code", 200)
                        text = getattr(response, "text", "")
                        if not is_challenge_response(status_code, text):
                            return response

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

                    h3_response = self._try_http3_request(url, merged_headers, timeout)
                    if h3_response is not None:
                        return h3_response

                    h2_response = self._try_stdlib_h2_request(url, merged_headers, timeout)
                    if h2_response is not None:
                        return h2_response

                    if (
                        self.enable_browser_fallback
                        and self._harvest_cookies_via_cdp_browser(url)
                    ):
                        self.log("Giai ma thanh cong qua System Browser CDP, thu lai request...")
                        merged_headers["User-Agent"] = self.user_agent
                        response = self._session.get(url, headers=merged_headers, timeout=timeout)
                        status_code = getattr(response, "status_code", 200)
                        text = getattr(response, "text", "")
                        if not is_challenge_response(status_code, text):
                            return response
                        if self._last_cdp_response is not None:
                            return self._last_cdp_response

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

    def _solve_gatekeeper_challenge(
        self, url: str, html_text: str, headers: dict, timeout: int = 15
    ) -> bool:
        """Solve built-in Gatekeeper SHA-256 Proof-of-Work challenge in pure Python."""
        cfg = parse_gatekeeper_challenge(html_text)
        if not cfg:
            return False
        nonce = solve_gatekeeper_pow(cfg["challenge_id"], cfg["difficulty_bits"])
        if nonce is None:
            return False
        verify_url = urljoin(url, cfg["verify_url"])
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        post_headers = dict(headers or {})
        post_headers["Content-Type"] = "application/json"
        if origin:
            post_headers["Origin"] = origin
        payload = {
            "challenge_id": cfg["challenge_id"],
            "ticket": cfg["ticket"],
            "nonce": nonce,
        }
        try:
            resp = self._session.post(verify_url, headers=post_headers, json=payload, timeout=timeout)
            if getattr(resp, "status_code", 0) == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("status") == "passed":
                    return True
        except Exception as exc:
            self.log(f"Khong the xac minh Gatekeeper PoW: {exc}")
        return False

    def _try_http3_request(self, url: str, headers: dict, timeout: int = 15):
        """Try HTTP/3 (QUIC) on a fresh curl_cffi session when HTTP/2 hits a challenge."""
        if (
            self.engine != "curl_cffi"
            or CURL_HTTP_V3 is None
            or cffi_requests is None
            or not isinstance(self._session, cffi_requests.Session)
            or "get" in getattr(self._session, "__dict__", {})
        ):
            return None
        try:
            h3_session = cffi_requests.Session(
                impersonate=self.impersonate, http_version=CURL_HTTP_V3
            )
            h3_session.headers.update({"User-Agent": self.user_agent})
            for k, v in self.get_cookies_dict().items():
                h3_session.cookies.set(k, v)
            resp = h3_session.get(
                url, headers=headers, timeout=timeout, http_version=CURL_HTTP_V3
            )
            status = getattr(resp, "status_code", 0)
            body = getattr(resp, "text", "")
            if 200 <= status < 400 and not is_challenge_response(status, body):
                self._session = h3_session
                self._prefer_http3 = True
                return resp
        except Exception:
            pass
        return None

    def _try_stdlib_h2_request(self, url: str, headers: dict, timeout: int = 15):
        """Pure-Python stdlib TLS 1.2 + HTTP/2 client for Termux when curl_cffi is unavailable."""
        if "get" in getattr(self._session, "__dict__", {}):
            return None
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        host = parsed.hostname
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        tls = None
        try:
            ctx = ssl.create_default_context()
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            ctx.set_ciphers("AES128-GCM-SHA256:AES256-GCM-SHA384")
            ctx.set_alpn_protocols(["h2", "http/1.1"])
            raw_sock = socket.create_connection((host, port), timeout=timeout)
            tls = ctx.wrap_socket(raw_sock, server_hostname=host)
            if tls.selected_alpn_protocol() != "h2":
                return None

            settings_payload = struct.pack("!HIHIHIHI", 1, 65536, 2, 0, 4, 6291456, 6, 262144)
            settings_frame = struct.pack("!I B B I", len(settings_payload), 4, 0, 0)[1:] + settings_payload
            win_frame = struct.pack("!I B B I I", 4, 8, 0, 0, 15663105)[1:]
            tls.sendall(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n" + settings_frame + win_frame)

            ua = (headers or {}).get("User-Agent") or self.user_agent
            hdrs = (
                _encode_hpack_literal(":method", "GET")
                + _encode_hpack_literal(":authority", host)
                + _encode_hpack_literal(":scheme", "https")
                + _encode_hpack_literal(":path", path)
                + _encode_hpack_literal("user-agent", ua)
                + _encode_hpack_literal("accept", "*/*")
            )
            referer = (headers or {}).get("Referer") or (headers or {}).get("referer")
            if referer:
                hdrs += _encode_hpack_literal("referer", referer)
            cookies_dict = self.get_cookies_dict()
            if "cf_clearance" in cookies_dict:
                cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
                hdrs += _encode_hpack_literal("cookie", cookie_str)

            tls.sendall(struct.pack("!I B B I", len(hdrs), 1, 0x05, 1)[1:] + hdrs)
            body = bytearray()
            status = 200
            while True:
                fh = bytearray()
                while len(fh) < 9:
                    chunk = tls.recv(9 - len(fh))
                    if not chunk:
                        break
                    fh.extend(chunk)
                if len(fh) < 9:
                    break
                flen = (fh[0] << 16) | (fh[1] << 8) | fh[2]
                ftype, fflags = fh[3], fh[4]
                fp = bytearray()
                while len(fp) < flen:
                    c = tls.recv(flen - len(fp))
                    if not c:
                        break
                    fp.extend(c)
                if ftype == 4 and not (fflags & 0x01):
                    tls.sendall(struct.pack("!I B B I", 0, 4, 0x01, 0)[1:])
                elif ftype == 1 and fp:
                    idx = 0
                    while idx < len(fp) and (fp[idx] & 0xE0) == 0x20:
                        if (fp[idx] & 0x1F) == 0x1F:
                            idx += 1
                            while idx < len(fp) and (fp[idx] & 0x80):
                                idx += 1
                        idx += 1
                    if idx < len(fp):
                        sb = fp[idx]
                        if sb == 0x88:
                            status = 200
                        elif sb == 0x8D:
                            status = 404
                        else:
                            status = 403
                elif ftype == 0:
                    body.extend(fp)
                    if flen > 0:
                        w = struct.pack("!I", flen)
                        tls.sendall(struct.pack("!I B B I", 4, 8, 0, 0)[1:] + w)
                        tls.sendall(struct.pack("!I B B I", 4, 8, 0, 1)[1:] + w)
                    if fflags & 0x01:
                        break
                elif ftype in (3, 7):
                    break

            raw_bytes = bytes(body)
            if not raw_bytes:
                return None
            text = raw_bytes.decode("utf-8", errors="replace")
            if status in (200, 404) and not is_challenge_response(status, text):
                self._prefer_stdlib_h2 = True
                return _SimpleHTTPResponse(status_code=status, content=raw_bytes, text=text)
        except Exception:
            pass
        finally:
            if tls is not None:
                try:
                    tls.close()
                except Exception:
                    pass
        return None

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

    def _harvest_cookies_via_cdp_browser(self, url: str) -> bool:
        """Harvest clearance cookies and User-Agent via system Chromium/Chrome/Edge CDP."""
        if "get" in getattr(self._session, "__dict__", {}):
            return False
        browser_bin = _find_system_chromium_binary()
        if not browser_bin:
            return False

        self.log("Dang khoi dong System Browser CDP de giai ma xac minh...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        user_data_dir = tempfile.mkdtemp(prefix="novel_cdp_")
        proc = None
        self._last_cdp_response = None
        try:
            proc = subprocess.Popen(
                _build_cdp_browser_args(browser_bin, user_data_dir, port, url, self.user_agent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            base_dom = _base_domain(url)
            ws_url = None
            for _ in range(15):
                time.sleep(1.5)
                try:
                    raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3).read().decode("utf-8")
                    tabs = json.loads(raw)
                except Exception:
                    continue
                page_tabs = [
                    t for t in tabs
                    if t.get("type") == "page" and base_dom in (t.get("url") or "").lower()
                ]
                if not page_tabs:
                    continue
                title = page_tabs[0].get("title") or ""
                if title and "just a moment" not in title.lower() and "attention required" not in title.lower():
                    ws_url = page_tabs[0].get("webSocketDebuggerUrl")
                    if ws_url:
                        break

            if not ws_url:
                return False

            cookies = _cdp_ws_call(ws_url, "Network.getAllCookies").get("cookies", [])
            ua_res = _cdp_ws_call(
                ws_url,
                "Runtime.evaluate",
                {"expression": "navigator.userAgent", "returnByValue": True},
            )
            html_res = _cdp_ws_call(
                ws_url,
                "Runtime.evaluate",
                {"expression": "document.documentElement.outerHTML", "returnByValue": True},
            )
            browser_ua = ((ua_res.get("result") or {}).get("value") or "").replace(
                "HeadlessChrome/", "Chrome/"
            )
            page_html = (html_res.get("result") or {}).get("value") or ""
            if page_html and not is_challenge_response(200, page_html):
                self._last_cdp_response = _SimpleHTTPResponse(
                    status_code=200,
                    content=page_html.encode("utf-8"),
                    text=page_html,
                )

            domain_cookies = [
                {"name": c["name"], "value": c["value"], "domain": c.get("domain")}
                for c in cookies
                if c.get("name") and c.get("value") and base_dom in (c.get("domain") or base_dom).lower()
            ]
            if not domain_cookies and self._last_cdp_response is None:
                return False

            if browser_ua:
                self.user_agent = browser_ua
                if hasattr(self._session, "headers"):
                    self._session.headers.update({"User-Agent": browser_ua})
            for cookie in domain_cookies:
                self.set_cookie(cookie["name"], cookie["value"], domain=cookie.get("domain"))

            if domain_cookies:
                _DOMAIN_CLEARANCE_CACHE[base_dom] = {
                    "user_agent": self.user_agent,
                    "cookies": domain_cookies,
                }
            self.log(f"Da dong bo {len(domain_cookies)} cookies tu System Browser CDP.")
            return True
        except Exception as exc:
            self.log(f"Khong the giai ma bang System Browser CDP: {exc}")
            return False
        finally:
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            shutil.rmtree(user_data_dir, ignore_errors=True)

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
