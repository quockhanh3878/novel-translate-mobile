"""Book metadata extraction, manual overrides, Resume and exported files; no API fees."""

import json
import os
from pathlib import Path
import tempfile
import threading
import sys
import unittest
from unittest.mock import Mock, patch
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import novel_metadata as metadata
import build_epub
import build_pdf
from path_resolver import resolve_pipeline_paths

PROJECT = Path(__file__).resolve().parent
DC = "{http://purl.org/dc/elements/1.1/}"


def chapter(title, text):
    return f"=== {title} ===\n\n{text}\n\n" + "=" * 40 + "\n\n"


class BookMetadataTests(unittest.TestCase):
    def test_cli_uses_url_identity_when_title_and_raw_are_omitted(self):
        import pipeline
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            os.chdir(directory)
            try:
                url = "https://www.uukanshu.cc/book/11966/"
                expected = resolve_pipeline_paths(url)
                with patch.object(sys, "argv", ["pipeline.py", "--start-url", url, "--crawl-only"]), patch.object(
                    metadata, "fetch_book_metadata", return_value={"original_title": "Source / title", "original_author": "Source author"}
                ), patch.object(pipeline, "crawl_novel", return_value=0) as crawl:
                    pipeline.main()
                self.assertEqual(crawl.call_args.args[1], str(expected["raw_path"]))
                profile = metadata.load_profile(expected["translated_path"])
                self.assertEqual(profile["display_title"], "Source / title")
                self.assertEqual(profile["author"], "Source author")
            finally:
                os.chdir(previous)

    def test_extract_explicit_source_information(self):
        html = (PROJECT / "test_data/uukanshu/book_11966.html").read_text(encoding="utf-8")
        data = metadata.parse_book_metadata(html, catalog=True)
        self.assertEqual(data["original_title"], "生活系遊戲")
        self.assertEqual(data["original_author"], "佚名")
        self.assertEqual(data["publication_date"], "")
        requested = []

        def fetch(url):
            requested.append(url)
            return Mock(status_code=200, content=html.encode())

        data = metadata.fetch_book_metadata("https://uukanshu.cc/book/11966/7364613.html", fetcher=fetch)
        self.assertTrue(requested[0].endswith("/book/11966/"))
        self.assertEqual(data["original_title"], "生活系遊戲")
        self.assertFalse(metadata.parse_book_metadata('<h1>Chapter 1</h1>')["original_title"])
        linked = metadata.parse_book_metadata('<script type="application/ld+json">' + json.dumps({
            "@type": "Book", "name": "Source title", "author": {"name": "Source author"},
            "datePublished": "2020-01-02"}) + '</script>')
        self.assertEqual(linked["original_author"], "Source author")
        self.assertEqual(linked["publication_date"], "2020-01-02")
        wa01 = "https://www.wa01.com/novel/pagea/qingshan-huishuohuadezhouzi_1.html"
        target = metadata.book_page_url(wa01)
        self.assertEqual(target, "https://www.wa01.com/novel/chapters/qingshan-huishuohuadezhouzi")
        self.assertEqual(metadata.source_identity(wa01), metadata.source_identity(target))
        chapter_date = metadata.parse_book_metadata('<meta property="article:published_time" content="2026-01-01">')
        self.assertEqual(chapter_date["publication_date"], "")

    def test_manual_overrides_and_stable_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = resolve_pipeline_paths("https://www.uukanshu.cc/book/11966/", output_dir=directory)
            raw, translated = paths["raw_path"], paths["translated_path"]
            original = {"original_title": "Source title", "original_author": "Source author"}
            first = metadata.prepare_profile(raw, translated, "https://uukanshu.cc/book/11966/1.html",
                                             title="Tên Việt", author="Tác giả đã sửa", source_info=original)
            resumed = metadata.prepare_profile(raw, translated, "https://www.uukanshu.cc/book/11966/2.html",
                                               source_info={**original, "original_title": "New source title"})
            self.assertEqual(resumed["display_title"], "Tên Việt")
            self.assertEqual(resumed["author"], "Tác giả đã sửa")
            self.assertEqual(resumed["book_id"], first["book_id"])
            self.assertEqual(resumed["created_at"], first["created_at"])
            renamed = resolve_pipeline_paths("https://www.uukanshu.cc/book/11966/", title="Tên Việt",
                                              output_dir=directory)
            self.assertEqual(renamed["raw_path"], raw)
            self.assertEqual(renamed["translated_path"], translated)
            with self.assertRaises(ValueError):
                metadata.prepare_profile(raw, translated, "https://www.uukanshu.cc/book/999/")

    def test_source_retry_upgrades_only_fallback_information(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw.txt"
            translated = Path(directory) / "raw.txt.viet.txt"
            first = metadata.prepare_profile(raw, translated)
            self.assertEqual(first["author"], "Unknown")
            source = {"original_title": "Source title", "original_author": "Source author"}
            retried = metadata.prepare_profile(raw, translated, source_info=source)
            self.assertEqual(retried["display_title"], "Source title")
            self.assertEqual(retried["author"], "Source author")
            metadata.prepare_profile(raw, translated, title="Manual", author="Manual author")
            retried = metadata.prepare_profile(raw, translated, source_info=source)
            self.assertEqual(retried["display_title"], "Manual")
            self.assertEqual(retried["author"], "Manual author")

    def test_epub_pdf_dates_metadata_and_incremental_rebuild(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            build_epub, "copy_to_downloads", lambda _: None
        ), patch.object(build_pdf, "copy_to_downloads", lambda _: None):
            raw = Path(directory) / "raw.txt"
            translated = Path(directory) / "raw.txt.viet.txt"
            raw.write_text(chapter("Chapter 1", "Source one") + chapter("Chapter 2", "Source two"), encoding="utf-8")
            translated.write_text(chapter("Chương 1", "Nội dung một."), encoding="utf-8")
            epub, pdf = str(Path(directory) / "book.epub"), str(Path(directory) / "book.pdf")
            with patch.object(metadata, "utc_now", return_value="2026-11-02T01:00:00Z"):
                profile = metadata.prepare_profile(raw, translated, "https://www.uukanshu.cc/book/11966/",
                                                    title="Tên Việt", author="Tác giả", model="test-model",
                                                    source_info={"original_title": "Source title"})
                build_epub.ensure_packaged(str(translated), epub, pdf, "Tên Việt", "Tác giả")
            with zipfile.ZipFile(epub) as archive:
                opf = ET.fromstring(archive.read(next(n for n in archive.namelist() if n.endswith(".opf"))))
            self.assertEqual(opf.find(".//" + DC + "identifier").text, profile["book_id"])
            self.assertEqual(opf.find(".//" + DC + "source").text, profile["source_url"])
            self.assertIsNone(opf.find(".//" + DC + "date"))
            modified = [node.text for node in opf.iter() if node.attrib.get("property") == "dcterms:modified"]
            self.assertEqual(modified, ["2026-11-02T01:00:00Z"])
            self.assertIn("test-model", opf.find(".//" + DC + "description").text)
            exported = metadata.load_profile(translated)
            self.assertFalse(exported["snapshot_complete"])
            pdf_bytes = Path(pdf).read_bytes()
            begin, end = pdf_bytes.index(b"<x:xmpmeta"), pdf_bytes.index(b"</x:xmpmeta>") + len(b"</x:xmpmeta>")
            xmp = ET.fromstring(pdf_bytes[begin:end])
            self.assertEqual(xmp.find(".//" + DC + "identifier").text, profile["book_id"])
            self.assertEqual(xmp.find(".//{http://ns.adobe.com/xap/1.0/}CreateDate").text,
                             "2026-11-02T01:00:00Z")
            self.assertEqual(build_epub.ensure_packaged(str(translated), epub, pdf, "Tên Việt", "Tác giả"),
                             {"epub_built": False, "pdf_built": False})
            translated.write_text(translated.read_text(encoding="utf-8") + chapter("Chương 2", "Nội dung hai."), encoding="utf-8")
            with patch.object(metadata, "utc_now", return_value="2026-11-02T02:00:00Z"):
                build_epub.ensure_packaged(str(translated), epub, pdf, "Tên Việt", "Tác giả")
            updated = metadata.load_profile(translated)
            self.assertEqual(updated["book_id"], profile["book_id"])
            self.assertEqual(updated["export_created_at"], "2026-11-02T01:00:00Z")
            self.assertEqual(updated["export_updated_at"], "2026-11-02T02:00:00Z")
            self.assertTrue(updated["snapshot_complete"])
            metadata.prepare_profile(raw, translated, model="new-model")
            self.assertFalse(build_epub.is_package_up_to_date(str(translated), epub))
            build_epub.ensure_packaged(str(translated), epub, pdf, "Tên Việt", "Tác giả")
            raw.write_text(raw.read_text(encoding="utf-8") + chapter("Chapter 3", "Source three"), encoding="utf-8")
            self.assertFalse(build_epub.is_package_up_to_date(str(translated), epub))

    def test_web_preview_and_saved_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            old_cwd = os.getcwd()
            os.chdir(directory)
            try:
                import web_gui
                server = web_gui.make_server("127.0.0.1", 0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                source = "https://www.uukanshu.cc/book/11966/"
                query = urllib.parse.urlencode({"input": source})
                try:
                    with patch.object(metadata, "fetch_book_metadata", return_value={
                        "original_title": "Source title", "original_author": "Source author"
                    }):
                        url = "http://127.0.0.1:%d/book_metadata?%s" % (server.server_address[1], query)
                        with urllib.request.urlopen(url) as response:
                            data = json.load(response)
                        self.assertEqual(data["title"], "Source title")
                        paths = resolve_pipeline_paths(source)
                        self.assertFalse(metadata.profile_path(paths["translated_path"]).exists())
                        metadata.run_metadata(paths["raw_path"], paths["translated_path"], source,
                                              "Manual title", "Manual author", model="deepseek-flash")
                        with urllib.request.urlopen(url) as response:
                            data = json.load(response)
                        self.assertEqual((data["title"], data["author"]), ("Manual title", "Manual author"))
                        self.assertEqual(data["translation_model"], "deepseek-flash")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
            finally:
                os.chdir(old_cwd)

    def test_start_is_reserved_during_metadata_lookup(self):
        import web_gui
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def pending(*args):
            calls.append(args)
            started.set()
            release.wait(5)
            finished.set()

        with web_gui.LOCK:
            previous = dict(web_gui.STATE)
            web_gui.STATE["running"] = False
        server = web_gui.make_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:%d/start" % server.server_address[1]
            body = urllib.parse.urlencode({"input": "fixture.txt", "title": "Fixture"}).encode()
            with patch.object(web_gui, "run_pipeline", side_effect=pending):
                with urllib.request.urlopen(url, data=body) as response:
                    self.assertEqual(response.status, 204)
                self.assertTrue(started.wait(2))
                with urllib.request.urlopen(url, data=body) as response:
                    self.assertEqual(response.status, 204)
                self.assertEqual(len(calls), 1)
                release.set()
                self.assertTrue(finished.wait(2))
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join()
            with web_gui.LOCK:
                web_gui.STATE.clear()
                web_gui.STATE.update(previous)


if __name__ == "__main__":
    unittest.main()
