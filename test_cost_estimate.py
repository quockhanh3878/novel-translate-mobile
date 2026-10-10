"""Offline tests for novel cost estimates and the web estimate endpoint."""

import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT)

import cost_estimate  # noqa: E402


def get_json(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def test_file_estimate(work):
    raw = Path(work) / "sample_raw.txt"
    translated = Path(str(raw) + ".viet.txt")
    raw.write_text(
        "=== TRUYEN ===\n\n"
        "=== Chuong 1 ===\nabc\nde\n\n========================================\n\n"
        "=== Chuong 2 ===\n1234567\n\n========================================\n",
        encoding="utf-8",
    )
    translated.write_text(
        "=== TRUYEN ===\n\n"
        "=== Chuong 1 ===\nban dich\n\n========================================\n",
        encoding="utf-8",
    )

    result = cost_estimate.estimate_file(raw, translated)
    assert result["available"] is True, result
    assert result["chapters"] == 2, result
    assert result["crawled_chapters"] == 2, result
    assert result["total_chars"] == 12, result
    assert result["translated_chapters"] == 1, result
    assert result["remaining_chars"] == 7, result
    assert result["cost_total"]["average"] == 12 * cost_estimate.RATE_AVERAGE
    assert result["cost_remaining"]["average"] == 7 * cost_estimate.RATE_AVERAGE

    no_thinking = cost_estimate.estimate_chars(1000, 10, no_thinking=True)
    low = cost_estimate.estimate_chars(1000, 10, reasoning_effort="low")
    peak = cost_estimate.estimate_chars(1000, 10, peak=True)
    medium = cost_estimate.estimate_chars(1000, 10)
    assert no_thinking["cost_total"]["average"] == medium["cost_total"]["average"] * 0.25
    assert low["cost_total"]["average"] == medium["cost_total"]["average"] * 0.95
    assert peak["cost_total"]["average"] == medium["cost_total"]["average"] * 2

    unknown = cost_estimate.estimate_chars(1000, 10, model="unknown-model")
    assert unknown["cost_total"] == medium["cost_total"]
    assert any("Chưa có bảng giá" in warning for warning in unknown["warnings"])
    assert cost_estimate.usd_from_usage({
        "prompt_cache_hit_tokens": 1_000_000,
        "prompt_cache_miss_tokens": 1_000_000,
        "completion_tokens": 1_000_000,
    }) == 0.753
    assert cost_estimate.usd_from_usage({"completion_tokens": 1_000_000}, peak=True) == 1.2


def test_invalid_files(work):
    missing = cost_estimate.estimate_file(Path(work) / "missing.txt")
    empty_path = Path(work) / "empty.txt"
    empty_path.write_text("", encoding="utf-8")
    empty = cost_estimate.estimate_file(empty_path)
    assert missing["available"] is False
    assert empty["available"] is False


def test_endpoint(work):
    raw = Path(work) / "endpoint_raw.txt"
    raw.write_text("=== T ===\n\n=== C1 ===\nabc\n\n========================================\n", encoding="utf-8")
    server = __import__("web_gui").make_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        query = urllib.parse.urlencode({
            "input": str(raw),
            "model": "unknown-model",
            "reasoning_effort": "max",
            "no_thinking": "0",
            "allow_peak": "0",
        })
        status, data = get_json(base, "/estimate?" + query)
        assert status == 200 and data["available"] is True, data
        assert data["chapters"] == 1 and data["crawled_chapters"] == 1 and data["total_chars"] == 3, data
        assert any("Chưa có bảng giá" in warning for warning in data["warnings"])

        # Test estimate co output_dir va phat hien file dich trong output_dir
        out_dir = Path(work) / "CustomEstimateDir"
        out_dir.mkdir(parents=True, exist_ok=True)
        custom_trans = out_dir / (raw.name + ".viet.txt")
        custom_trans.write_text("=== T ===\n\n=== C1 ===\nban dich\n\n========================================\n", encoding="utf-8")

        query_out = urllib.parse.urlencode({
            "input": str(raw),
            "output_dir": str(out_dir),
        })
        status, data = get_json(base, "/estimate?" + query_out)
        assert status == 200 and data["available"] is True, data
        assert data["translated_chapters"] == 1, data

        for bad_input in ("../web_gui.py", ".", "missing.txt"):
            status, data = get_json(base, "/estimate?" + urllib.parse.urlencode({"input": bad_input}))
            assert status in (200, 400) and data["available"] is False, (bad_input, status, data)

        status, data = get_json(base, "/estimate?" + urllib.parse.urlencode({
            "input": "https://example.invalid/book_1.html",
        }))
        assert status == 200 and data["available"] is False
        assert "cào" in data["reason"]
    finally:
        server.shutdown()
        server.server_close()


def test_key_balance():
    import web_gui

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "is_available": True,
                "balance_infos": [{
                    "currency": "CNY",
                    "total_balance": "12.50",
                    "granted_balance": "2.50",
                    "topped_up_balance": "10.00",
                }],
            }

    original_get = web_gui.requests.get
    original_key = os.environ.pop("DEEPSEEK_API_KEY", None)
    try:
        web_gui.requests.get = lambda url, headers, timeout: FakeResponse()
        result = web_gui.get_deepseek_balance("sk-test")
        assert result["available"] is True, result
        assert result["is_available"] is True, result
        assert result["balance_infos"][0]["total_balance"] == "12.50", result
        assert web_gui.get_deepseek_balance("")["available"] is False
    finally:
        web_gui.requests.get = original_get
        if original_key is not None:
            os.environ["DEEPSEEK_API_KEY"] = original_key


def test_spent_cost():
    import web_gui

    original = web_gui._worker_command
    try:
        fake = (
            "import sys; "
            "print('[usage] prompt_tokens=3000000 (cache_hit=1000000, "
            "cache_miss=1000000) completion_tokens=1000000 total_tokens=4000000)"
        )
        web_gui._worker_command = lambda: [sys.executable, "-u", "-c", fake]
        with web_gui.LOCK:
            web_gui.STATE["cost_spent"] = 99.0
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Gia", model="deepseek-flash")
        assert abs(web_gui.STATE["cost_spent"] - 0.753) < 1e-12, web_gui.STATE

        no_usage = "import sys; print('done')"
        web_gui._worker_command = lambda: [sys.executable, "-u", "-c", no_usage]
        web_gui.run_pipeline("truyen_tho.txt", "Truyen Gia", model="deepseek-flash")
        assert web_gui.STATE["cost_spent"] == 0.0, web_gui.STATE
    finally:
        web_gui._worker_command = original


def test_catalog_estimate():
    class FakeAdapter:
        calls = {"list": 0, "crawl": 0}

        def catalog_url(self, url):
            return "https://fake.test/book/1/"

        def list_chapters(self, url, log=print):
            self.calls["list"] += 1
            return [{"url": "https://fake.test/book/1/%d.html" % i, "title": "c%d" % i} for i in range(100)]

        def crawl_chapter(self, url, log=print):
            self.calls["crawl"] += 1
            return {"title": "t", "paragraphs": ["x" * 1000, "y" * 1000]}

    cost_estimate._CATALOG_CACHE.clear()
    sleeps = []
    adapter = FakeAdapter()
    result = cost_estimate.estimate_catalog("https://fake.test/book/1/", adapter, sleep=sleeps.append)
    assert result["available"] and result["chapters"] == 100 and result["total_chars"] == 200000, result
    assert abs(result["cost_total"]["average"] - 200000 * cost_estimate.RATE_AVERAGE) < 1e-9
    assert any("Chưa cào truyện" in w for w in result["warnings"]), result
    assert adapter.calls == {"list": 1, "crawl": cost_estimate.SAMPLE_CHAPTERS}, adapter.calls
    assert sleeps == [cost_estimate.SAMPLE_DELAY_SECONDS] * (cost_estimate.SAMPLE_CHAPTERS - 1), sleeps
    # doi model/muc suy luan dung cache, khong goi lai trang
    again = cost_estimate.estimate_catalog("https://fake.test/book/1/", adapter, no_thinking=True, sleep=sleeps.append)
    assert adapter.calls == {"list": 1, "crawl": cost_estimate.SAMPLE_CHAPTERS}, adapter.calls
    assert again["cost_total"]["average"] < result["cost_total"]["average"]

    # loi muc luc: available=false, nho loi ngan han (khong goi lai ngay), het han thi thu lai
    class Broken(FakeAdapter):
        def list_chapters(self, url, log=print):
            self.calls["list"] += 1
            return None

    cost_estimate._CATALOG_CACHE.clear()
    broken = Broken()
    broken.calls = {"list": 0, "crawl": 0}
    clock = [1000.0]
    for _ in range(2):
        r = cost_estimate.estimate_catalog("https://fake.test/book/1/", broken, now=lambda: clock[0])
        assert r["available"] is False and r["reason"], r
    assert broken.calls["list"] == 1, broken.calls
    clock[0] += cost_estimate.ERROR_CACHE_SECONDS + 1
    cost_estimate.estimate_catalog("https://fake.test/book/1/", broken, now=lambda: clock[0])
    assert broken.calls["list"] == 2, broken.calls
    cost_estimate._CATALOG_CACHE.clear()


def main():
    with tempfile.TemporaryDirectory() as work:
        old_cwd = os.getcwd()
        os.chdir(work)
        try:
            test_file_estimate(work)
            test_invalid_files(work)
            test_endpoint(work)
            test_spent_cost()
            test_catalog_estimate()
            test_key_balance()
        finally:
            os.chdir(old_cwd)
    print("OK: cost estimate va endpoint offline")


if __name__ == "__main__":
    main()
