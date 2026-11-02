"""Offline regressions for pagination, interrupted HTTP/2 and packaging reuse."""

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import build_epub as epub_module
import build_pdf as pdf_module
import hybrid_session
from sources import BiqugeTwAdapter


def h2_frame(kind, flags, payload, stream=1):
    return (len(payload).to_bytes(3, "big") + bytes([kind, flags])
            + stream.to_bytes(4, "big") + payload)


class FakeTLS:
    def __init__(self, data):
        self.data = data

    def selected_alpn_protocol(self):
        return "h2"

    def recv(self, size):
        result, self.data = self.data[:size], self.data[size:]
        return result

    def sendall(self, data):
        pass

    def close(self):
        pass


class AuditRegressions(unittest.TestCase):
    def test_pagination_with_previous_and_next_links(self):
        urls = [f"https://www.biquge.tw/book/1/100{suffix}.html"
                for suffix in ("", "_2", "_3", "_4")]
        pages = {}
        for index, url in enumerate(urls):
            links = f'<a href="{urls[index - 1]}">Previous</a>' if index else ""
            if index + 1 < len(urls):
                links += f'<a rel="next" href="{urls[index + 1]}">Next</a>'
            pages[url] = (f'<h1>Chapter 1</h1><div id="chaptercontent">'
                          f'<p>Page {index + 1} body.</p></div>'
                          f'<div class="read-page">{links}</div>').encode()
        calls = []

        def fetch(url):
            calls.append(url)
            return Mock(status_code=200, content=pages[url])

        result = BiqugeTwAdapter(fetcher=fetch).crawl_chapter(urls[0], log=lambda _: None)
        self.assertEqual(calls, urls)
        self.assertEqual(result["paragraphs"], [f"Page {i} body." for i in range(1, 5)])

    def h2_response(self, frames):
        session = hybrid_session.HybridCrawlerSession(log=lambda _: None)
        context = Mock()
        context.wrap_socket.return_value = FakeTLS(frames)
        with patch.object(hybrid_session.ssl, "create_default_context", return_value=context), patch.object(
            hybrid_session.socket, "create_connection", return_value=Mock()
        ):
            response = session._try_stdlib_h2_request("https://example.invalid/1.html", {})
        return session, response

    def test_h2_rejects_incomplete_responses(self):
        prefix = h2_frame(1, 4, b"\x88") + h2_frame(0, 0, b"partial body")
        tails = {
            "eof": b"",
            "reset": h2_frame(3, 0, struct.pack("!I", 2)),
            "goaway": h2_frame(7, 0, b"\0" * 8, stream=0),
            "short_frame_header": b"\x00\x00",
            "short_frame_body": h2_frame(0, 1, b"unfinished")[:-3],
        }
        for name, tail in tails.items():
            with self.subTest(name=name):
                session, response = self.h2_response(prefix + tail)
                self.assertIsNone(response)
                self.assertFalse(session._prefer_stdlib_h2)

    def test_h2_accepts_complete_response(self):
        frames = (h2_frame(1, 4, b"\x88") + h2_frame(0, 0, b"first ")
                  + h2_frame(0, 1, b"second"))
        session, response = self.h2_response(frames)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"first second")
        self.assertTrue(session._prefer_stdlib_h2)

    def test_packaging_rejects_corruption_and_refreshes_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            epub_module, "copy_to_downloads", lambda _: None
        ), patch.object(pdf_module, "copy_to_downloads", lambda _: None):
            root = Path(directory)
            source = root / "translated.txt"
            source.write_text("=== Chapter 1 ===\n\nHello world.\n\n" + "=" * 40 + "\n", encoding="utf-8")
            epub = root / "book.epub"
            pdf = root / "book.pdf"
            args = (str(source), str(epub), str(pdf))
            pdf.write_bytes(b"%PDF-")
            self.assertFalse(epub_module.is_package_up_to_date(str(source), str(pdf)))

            self.assertEqual(epub_module.ensure_packaged(*args, "Old title", "Old author"),
                             {"epub_built": True, "pdf_built": True})
            # Persisted evidence must also work in a fresh process.
            check = subprocess.run([
                sys.executable, "-c",
                "from build_epub import is_package_up_to_date as check; import sys; "
                "assert check(sys.argv[1], sys.argv[2]); assert check(sys.argv[1], sys.argv[3])",
                *args,
            ], cwd=str(Path(__file__).resolve().parent), capture_output=True, text=True, timeout=20)
            self.assertEqual(check.returncode, 0, check.stderr)

            self.assertEqual(epub_module.ensure_packaged(*args, "New title", "Old author"),
                             {"epub_built": True, "pdf_built": True})
            self.assertEqual(epub_module.ensure_packaged(*args, "New title", "New author"),
                             {"epub_built": True, "pdf_built": True})
            with zipfile.ZipFile(epub) as archive:
                opf = archive.read(next(n for n in archive.namelist() if n.endswith(".opf"))).decode()
                self.assertIn("New title", opf)
                self.assertIn("New author", opf)
            pdf_bytes = pdf.read_bytes()
            self.assertIn(b"New title", pdf_bytes)
            self.assertIn(b"New author", pdf_bytes)
            self.assertEqual(epub_module.ensure_packaged(*args, "New title", "New author"),
                             {"epub_built": False, "pdf_built": False})

            # Same size and timestamp: a digest must still detect damaged output.
            original_stat = pdf.stat()
            pdf.write_bytes(pdf_bytes[:10] + b"X" + pdf_bytes[11:])
            os.utime(pdf, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            self.assertFalse(epub_module.is_package_up_to_date(str(source), str(pdf)))
            self.assertEqual(epub_module.ensure_packaged(*args, "New title", "New author"),
                             {"epub_built": False, "pdf_built": True})
            pdf.write_bytes(pdf.read_bytes()[:-30])
            self.assertFalse(epub_module.is_package_up_to_date(str(source), str(pdf)))


if __name__ == "__main__":
    unittest.main()
