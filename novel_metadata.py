"""Source book information and persistent metadata shared by all entrypoints."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.parse import urlsplit, urlunsplit
import uuid

from bs4 import BeautifulSoup

_LOCK = threading.RLock()
_SOURCE_CACHE = {}


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def profile_path(translated_file):
    return Path(str(translated_file).rsplit(".", 1)[0] + "_book.json")


def load_profile(translated_file):
    path = profile_path(translated_file)
    if not path.exists():
        return {}
    # Do not overwrite an unreadable profile and lose manually edited information.
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Ho so truyen khong hop le: " + str(path))
    return data


def _save_profile(translated_file, data):
    path = profile_path(translated_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def book_page_url(url):
    from sources import find_adapter
    adapter = find_adapter(url)
    target = (adapter.catalog_url(url) if adapter else None) or url
    parsed = urlsplit(target)
    if (parsed.hostname or "").lower() in ("wa01.com", "www.wa01.com", "m.wa01.com"):
        match = re.fullmatch(r"/novel/pagea/(.+)_\d+\.html?", parsed.path)
        if match:
            target = urlunsplit((parsed.scheme, parsed.netloc, "/novel/chapters/" + match.group(1), "", ""))
    return target


def source_identity(url):
    target = book_page_url(url)
    parsed = urlsplit(target)
    host = (parsed.hostname or "").lower()
    host = re.sub(r"^(?:www|m)\.", "", host)
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))


def parse_book_metadata(html, catalog=False):
    soup = BeautifulSoup(html, "html.parser")
    from hybrid_session import has_challenge_indicator
    if has_challenge_indicator(html):
        return {}

    def meta(*names):
        for name in names:
            node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if node and node.get("content", "").strip():
                return node["content"].strip()
        return ""

    title = meta("og:novel:book_name", "book_name", "novel:book_name")
    author = meta("og:novel:author", "book:author", "author", "novel:author")
    genre = meta("og:novel:category")
    published = meta("book:release_date", "og:novel:publication_date")
    # JSON-LD is another explicit source; never infer a name with an AI call.
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            objects = json.loads(node.string or node.get_text())
        except (ValueError, TypeError):
            continue
        objects = objects if isinstance(objects, list) else [objects]
        for item in objects:
            if not isinstance(item, dict) or item.get("@type") not in ("Book", "Novel"):
                continue
            title = title or str(item.get("name") or "")
            person = item.get("author")
            if isinstance(person, list):
                person = person[0] if person else None
            author = author or (str(person.get("name") or "") if isinstance(person, dict)
                                else person if isinstance(person, str) else "")
            published = published or str(item.get("datePublished") or "")
    if catalog:
        title = title or meta("og:title")
        if not title:
            node = soup.select_one("h1.booktitle, .book-info h1, #info h1, .info h1, h1")
            title = node.get_text(" ", strip=True) if node else ""
        if not author:
            node = soup.select_one('[itemprop="author"], .book-author, .author')
            author = node.get_text(" ", strip=True) if node else ""
        if not author:
            for line in soup.get_text("\n", strip=True).splitlines():
                match = re.fullmatch(r"(?:作者|作\s*者|Author)\s*[:：]\s*(.{1,80})", line.strip(), re.I)
                if match:
                    author = match.group(1)
                    break
    author = re.sub(r"^(?:作者|作\s*者|Author)\s*[:：]\s*", "", author, flags=re.I).strip()
    if published:
        try:
            datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            published = ""
    return {"original_title": title.strip(), "original_author": author,
            "genre": genre, "publication_date": published}


def fetch_book_metadata(url, fetcher=None):
    from sources import find_adapter, Shuba69Adapter
    from hybrid_session import HybridCrawlerSession
    adapter = find_adapter(url)
    host = (urlsplit(url).hostname or "").lower()
    if not adapter and host not in ("wa01.com", "www.wa01.com", "m.wa01.com"):
        return {}
    page_url = book_page_url(url)
    catalog_url = page_url if adapter or "/novel/chapters/" in page_url else None
    target = catalog_url or url
    identity = source_identity(url)
    with _LOCK:
        cached = _SOURCE_CACHE.get(identity)
        if fetcher is None and cached and time.monotonic() - cached[0] < 300:
            return dict(cached[1])
    session = None
    try:
        if fetcher:
            response = fetcher(target)
        else:
            session = HybridCrawlerSession(enable_browser_fallback=False, log=lambda _: None)
            response = session.get(target, timeout=10, retries=0)
        if response.status_code != 200:
            return {}
        html = Shuba69Adapter._response_content(response)
        info = parse_book_metadata(html, catalog=bool(catalog_url))
        info.update(source_url=target, source_identity=identity, source_site=host)
        if fetcher is None:
            with _LOCK:
                _SOURCE_CACHE[identity] = (time.monotonic(), dict(info))
        return info
    except Exception:
        # Metadata lookup failure must not prevent manual entry or translation.
        return {}
    finally:
        if session is not None:
            close = getattr(session._session, "close", None)
            if close:
                close()


def prepare_profile(raw_file, translated_file, source_url="", title=None, author=None,
                    source_info=None, model=None):
    from crawler import guess_title
    with _LOCK:
        data = load_profile(translated_file)
        now = utc_now()
        identity = source_identity(source_url) if source_url else ""
        if identity and data.get("source_identity") and identity != data["source_identity"]:
            raise ValueError("File nay da thuoc mot truyen khac. Hay chon thu muc dau ra rieng.")
        data.setdefault("book_id", "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, identity)
                                                    if identity else uuid.uuid4()))
        data.setdefault("created_at", now)
        data.setdefault("version", 1)
        data.setdefault("language", "vi")
        data["raw_path"] = str(Path(raw_file).resolve()) if raw_file else data.get("raw_path", "")
        if source_url:
            data.setdefault("crawl_started_at", now)
            data.update(source_url=source_url, source_identity=identity,
                        source_site=urlsplit(source_url).hostname or "")
        for key in ("original_title", "original_author", "genre", "publication_date"):
            value = (source_info or {}).get(key)
            if value:
                data[key] = value
        for field, explicit, original, fallback in (
            ("display_title", title, "original_title", guess_title(str(raw_file or translated_file))),
            ("author", author, "original_author", "Unknown"),
        ):
            origin_key = field + "_origin"
            if (explicit or "").strip():
                data[field], data[origin_key] = explicit.strip(), "manual"
            elif data.get(field) and data.get(origin_key, "manual") == "manual":
                pass
            elif data.get(original):
                data[field], data[origin_key] = data[original], "source"
            else:
                data[field], data[origin_key] = data.get(field) or fallback, "fallback"
        if model:
            data["translation_model"] = model
        for key, path in (("source", data.get("raw_path")), ("translation", translated_file)):
            if path and Path(path).is_file():
                stat = Path(path).stat()
                signature = [stat.st_size, stat.st_mtime_ns]
                if data.get(key + "_signature") != signature:
                    data[key + "_signature"] = signature
                    data[key + "_updated_at"] = now
        _save_profile(translated_file, data)
        return data


def export_metadata(translated_file, title, author):
    from crawler import parse_chapters, is_novel_title_entry
    previous = load_profile(translated_file)
    data = prepare_profile(previous.get("raw_path", ""), translated_file,
                           title=None if title == previous.get("display_title") else title,
                           author=None if author == previous.get("author") else author)
    chapters = parse_chapters(translated_file)
    data["exported_chapters"] = len(chapters) - int(is_novel_title_entry(chapters, 0))
    data["source_chapters"] = None
    if data.get("raw_path") and Path(data["raw_path"]).is_file():
        raw = parse_chapters(data["raw_path"])
        data["source_chapters"] = len(raw) - int(is_novel_title_entry(raw, 0))
    # These counts describe the local snapshot, never claim the online novel is complete.
    data["snapshot_complete"] = (data["source_chapters"] is not None and
                                 data["exported_chapters"] == data["source_chapters"])
    data.setdefault("export_created_at", utc_now())
    data["export_updated_at"] = utc_now()
    _save_profile(translated_file, data)
    return data


def metadata_fingerprint(translated_file):
    data = load_profile(translated_file)
    keys = ("book_id", "original_title", "original_author", "genre", "publication_date",
            "source_url", "language", "translation_model", "raw_path", "source_signature")
    values = {k: data.get(k) for k in keys}
    raw = data.get("raw_path")
    if raw and Path(raw).is_file():
        stat = Path(raw).stat()
        values["source_signature"] = [stat.st_size, stat.st_mtime_ns]
    elif raw:
        values["source_signature"] = None
    payload = json.dumps(values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def describe_export(data):
    parts = ["Bản dịch tiếng Việt", "ID: " + data["book_id"],
             "Số chương đã xuất: " + str(data["exported_chapters"]),
             "Tạo bản xuất: " + data["export_created_at"], "Cập nhật bản xuất: " + data["export_updated_at"]]
    parts.append("Phạm vi: dữ liệu đã cào, chưa xác nhận đủ toàn truyện.")
    for key, label in (("original_title", "Tên gốc"), ("original_author", "Tác giả gốc"),
                       ("source_url", "Nguồn"), ("translation_model", "Model ở lần chạy gần nhất")):
        if data.get(key):
            parts.append(label + ": " + str(data[key]))
    if not data["snapshot_complete"]:
        parts.append("Bản dịch đang cập nhật; có thể chưa đủ chương.")
    return "\n".join(parts)


def run_metadata(raw_file, translated_file, source_url="", title=None, author=None, model=None):
    existing = load_profile(translated_file)
    missing_source = not existing.get("original_title") or not existing.get("original_author")
    source_info = fetch_book_metadata(source_url) if source_url and missing_source else {}
    return prepare_profile(raw_file, translated_file, source_url, title, author, source_info, model)


def preview_metadata(input_value, title="", output_dir=""):
    from path_resolver import resolve_pipeline_paths
    paths = resolve_pipeline_paths(input_value, title=title, output_dir=output_dir)
    existing = load_profile(paths["translated_path"])
    if (paths["is_url"] and existing.get("source_identity") and
            existing["source_identity"] != source_identity(input_value)):
        raise ValueError("File nay da thuoc mot truyen khac. Hay chon thu muc dau ra rieng.")
    missing_source = not existing.get("original_title") or not existing.get("original_author")
    info = fetch_book_metadata(input_value) if paths["is_url"] and missing_source else {}
    data = {**info, **existing}
    saved_title = existing.get("display_title") if existing.get("display_title_origin") != "fallback" else ""
    data["title"] = saved_title or info.get("original_title") or existing.get("display_title") or ""
    saved_author = existing.get("author") if existing.get("author") != "Unknown" else ""
    data["author"] = saved_author or info.get("original_author") or ""
    data["available"] = bool(data["title"] or data["author"])
    if not data["available"]:
        data["reason"] = "Không lấy được tên hoặc tác giả từ nguồn; anh có thể nhập thủ công."
    # Keep internal paths and fingerprints out of the product display.
    return {key: data.get(key, "") for key in (
        "available", "title", "author", "original_title", "original_author", "genre",
        "source_url", "book_id", "publication_date", "reason", "export_created_at",
        "export_updated_at", "exported_chapters", "translation_model")}
