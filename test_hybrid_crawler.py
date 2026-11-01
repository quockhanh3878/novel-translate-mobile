"""Tests for Hybrid Crawler Session and Anti-Bot Mechanism."""

from unittest.mock import MagicMock, patch
import hybrid_session
from hybrid_session import (
    HybridCrawlerSession,
    CrawlBlockedError,
    DEFAULT_USER_AGENT,
    is_challenge_response,
)
import crawler
from sources import UukanshuAdapter


def test_ac1_engine_initialization_and_fallback():
    """AC 1: Fast client initializes with curl_cffi or falls back to cloudscraper/requests."""
    session = HybridCrawlerSession()
    assert session.engine in ("curl_cffi", "cloudscraper", "requests")

    # Simulate curl_cffi unavailable
    with patch.object(hybrid_session, "HAS_CURL_CFFI", False):
        with patch.object(hybrid_session, "HAS_CLOUDSCRAPER", True):
            fallback_session = HybridCrawlerSession()
            assert fallback_session.engine == "cloudscraper"

    # Simulate both curl_cffi and cloudscraper unavailable
    with patch.object(hybrid_session, "HAS_CURL_CFFI", False):
        with patch.object(hybrid_session, "HAS_CLOUDSCRAPER", False):
            std_session = HybridCrawlerSession()
            assert std_session.engine == "requests"


def test_ac2_cookie_persistence_and_sync():
    """AC 2: Cookies and User-Agent persist accurately across engines and requests."""
    for use_cffi, use_cs in ((True, True), (False, True), (False, False)):
        with patch.object(hybrid_session, "HAS_CURL_CFFI", use_cffi and hybrid_session.HAS_CURL_CFFI):
            with patch.object(hybrid_session, "HAS_CLOUDSCRAPER", use_cs and hybrid_session.HAS_CLOUDSCRAPER):
                session = HybridCrawlerSession()
                assert session.get_cookie("cf_clearance") is None
                session.set_cookie("cf_clearance", "test_token_12345", domain=".example.com")
                assert session.get_cookie("cf_clearance") == "test_token_12345"
                assert session.get_cookies_dict().get("cf_clearance") == "test_token_12345"


def test_tier2_http_429_exponential_backoff():
    """Tier 2: Pure HTTP 429 rate-limit triggers exponential backoff before succeeding."""
    logs = []
    delays = []
    session = HybridCrawlerSession(enable_browser_fallback=False, log=logs.append)

    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.text = "Too Many Requests"

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.text = "<html><body>OK</body></html>"

    session._session.get = MagicMock(side_effect=[rate_limited, rate_limited, ok_response])

    with patch.object(hybrid_session.time, "sleep", side_effect=delays.append):
        resp = session.get("https://example.com/novel/1.html", retries=2)
        assert resp.status_code == 200
        assert delays == [2.0, 4.0]
        assert session._session.get.call_count == 3


def test_ac3_challenge_detection_and_browser_fallback():
    """AC 3: Challenge response triggers browser harvester and retries successfully."""
    logs = []
    session = HybridCrawlerSession(enable_browser_fallback=True, log=logs.append)

    challenge_response = MagicMock()
    challenge_response.status_code = 403
    challenge_response.text = "Just a moment... cf-turnstile"

    success_response = MagicMock()
    success_response.status_code = 200
    success_response.text = "<html><div class='title'>Chuong 1</div><div class='content'><p>Noi dung</p></div></html>"
    success_response.content = success_response.text.encode("utf-8")

    # Mock _session.get to return challenge first, then success after cookie harvest
    mock_get = MagicMock(side_effect=[challenge_response, success_response])
    session._session.get = mock_get

    with patch.object(hybrid_session, "HAS_PLAYWRIGHT", True):
        with patch.object(session, "_harvest_and_sync_cookies", return_value=True) as mock_harvest:
            resp = session.get("https://example.com/novel/1.html")
            assert resp.status_code == 200
            mock_harvest.assert_called_once_with("https://example.com/novel/1.html")
            assert any("Giai ma thanh cong" in log for log in logs)


def test_tier3_harvest_and_sync_cookies_playwright():
    """Tier 3: _harvest_and_sync_cookies waits for challenge clearance and syncs cf_clearance."""
    logs = []
    session = HybridCrawlerSession(enable_browser_fallback=True, log=logs.append)

    fake_page = MagicMock()
    fake_page.content.side_effect = [
        "<html><body>Just a moment... cf-turnstile</body></html>",
        "<html><body><div class='content'>Solved</div></body></html>",
    ]

    fake_context = MagicMock()
    fake_context.new_page.return_value = fake_page
    fake_context.cookies.side_effect = [
        [],
        [{"name": "cf_clearance", "value": "harvested_token_999", "domain": ".example.com"}],
    ]

    fake_browser = MagicMock()
    fake_browser.new_context.return_value = fake_context

    fake_pw = MagicMock()
    fake_pw.chromium.launch.return_value = fake_browser
    fake_pw_cm = MagicMock()
    fake_pw_cm.__enter__.return_value = fake_pw
    fake_pw_cm.__exit__.return_value = False

    with patch.object(hybrid_session, "sync_playwright", return_value=fake_pw_cm):
        with patch.object(hybrid_session, "stealth_sync", None):
            with patch.object(hybrid_session.time, "sleep", return_value=None):
                solved = session._harvest_and_sync_cookies("https://example.com/novel/1.html")
                assert solved is True
                assert session.get_cookie("cf_clearance") == "harvested_token_999"
                fake_browser.new_context.assert_called_once_with(user_agent=session.user_agent)


def test_ac3_challenge_blocked_when_fallback_unavailable():
    """AC 3b: When browser fallback is disabled/unavailable and challenge occurs, raise CrawlBlockedError."""
    session = HybridCrawlerSession(enable_browser_fallback=False)

    challenge_response = MagicMock()
    challenge_response.status_code = 403
    challenge_response.text = "browser verification required"
    session._session.get = MagicMock(return_value=challenge_response)

    try:
        session.get("https://example.com/novel/1.html")
    except CrawlBlockedError as exc:
        assert "HTTP 403" in str(exc)
        assert "nhap file HTML" in str(exc)
    else:
        raise AssertionError("Expected CrawlBlockedError when browser fallback is disabled")


def test_crawler_integration_and_user_agent_consistency():
    """Verify crawler.py uses HybridCrawlerSession without overriding its persistent User-Agent."""
    messages = []
    fake_success = MagicMock()
    fake_success.status_code = 200
    fake_success.content = (
        b"<html><div class='title'>Chuong Test</div>"
        b"<div class='content'><p>Doan 1</p><p>Doan 2</p></div></html>"
    )
    fake_success.text = fake_success.content.decode("utf-8")

    session = HybridCrawlerSession(user_agent=DEFAULT_USER_AGENT)
    captured_headers = []

    def fake_session_get(url, headers=None, timeout=15):
        captured_headers.append(headers)
        return fake_success

    session.get = MagicMock(side_effect=fake_session_get)

    for idx in (1, 2):
        result = crawler.crawl_chapter(
            f"https://www.wa01.com/novel/pagea/sample_{idx}.html",
            log=messages.append,
            session=session,
        )
        assert result is not None
        assert result["title"] == "Chuong Test"
        assert result["paragraphs"] == ["Doan 1", "Doan 2"]

    # crawler.crawl_chapter must not override session's User-Agent with random USER_AGENTS
    assert captured_headers == [None, None]
    assert session._session.headers.get("User-Agent") == DEFAULT_USER_AGENT


def test_uukanshu_adapter_uses_hybrid_session():
    """Verify UukanshuAdapter uses HybridCrawlerSession by default when no custom fetcher is given."""
    adapter = UukanshuAdapter()
    assert isinstance(adapter.session, HybridCrawlerSession)


def main():
    test_ac1_engine_initialization_and_fallback()
    test_ac2_cookie_persistence_and_sync()
    test_tier2_http_429_exponential_backoff()
    test_ac3_challenge_detection_and_browser_fallback()
    test_tier3_harvest_and_sync_cookies_playwright()
    test_ac3_challenge_blocked_when_fallback_unavailable()
    test_crawler_integration_and_user_agent_consistency()
    test_uukanshu_adapter_uses_hybrid_session()
    print("OK: all hybrid crawler session and integration tests passed.")


if __name__ == "__main__":
    main()

