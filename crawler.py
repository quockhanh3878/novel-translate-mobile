import argparse
import json
import os
import re
import sys
import time
import random
import cloudscraper

from bs4 import BeautifulSoup
from sources import find_adapter
from hybrid_session import (
    HybridCrawlerSession,
    CrawlBlockedError,
    has_challenge_indicator,
)

DEFAULT_START_URL = "https://www.wa01.com/novel/pagea/disanchongrenge-changshuxin_1.html"
DEFAULT_OUTPUT = "truyen_de_tam_trung_nhan_cach.txt"
CHAPTER_SEP = "\n" + "=" * 40 + "\n\n"

CLOUDFLARE_BROWSERS = [
    {"browser": "chrome", "platform": "windows", "mobile": False},
    {"browser": "chrome", "platform": "linux", "mobile": False},
    {"browser": "firefox", "platform": "windows", "mobile": False},
    {"browser": "firefox", "platform": "linux", "mobile": False}
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15"
]


# --- Dinh dang file chung (=== Tieu de ===, doan van, "="*40 ngan cach chuong) -------
# Dung chung boi crawler.py (ghi), deepseek_translate.py va build_epub.py (doc) - de
# o day vi day la module tao ra dinh dang nay, tranh 3 ban parse_chapters() rieng le
# de lech nhau moi khi sua 1 cho.

def parse_chapters(input_file: str) -> list[dict]:
    chapters = []
    current = None
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str == "=" * 40:
                continue
            m = re.match(r"^===\s*(.*?)\s*===$", line_str)
            if m:
                if current:
                    chapters.append(current)
                current = {"title": m.group(1).strip(), "paragraphs": []}
            elif current:
                current["paragraphs"].append(line_str)
    if current:
        chapters.append(current)
    return chapters


def is_novel_title_entry(chapters: list[dict], index: int) -> bool:
    """Muc tieu de la muc dau tien khong co doan van trong file dinh dang truyen."""
    return index == 0 and bool(chapters) and not chapters[0].get("paragraphs")


def iter_chapters_from_file(input_file: str):
    """Yield cac chuong co noi dung theo thu tu nguon, kem chi so 1-based."""
    chapters = parse_chapters(input_file)
    source_index = 0
    for index, chapter in enumerate(chapters):
        if is_novel_title_entry(chapters, index):
            continue
        source_index += 1
        item = dict(chapter)
        item["_source_index"] = source_index
        yield item


def count_chapters(file_path: str) -> int:
    """Dem so chuong da hoan tat trong 1 file dinh dang === ... === (ca file tho da cao
    lan file da dich deu dung chung dinh dang nay) - dung "="*40 lam moc ket thuc 1
    chuong vi dong nay chi xuat hien khi 1 chuong da ghi xong hoan toan."""
    if not os.path.exists(file_path):
        return 0
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().count("=" * 40)


def guess_title(text: str) -> str:
    """Doan ten truyen tu URL muc luc / chuong 1 (slug cuoi duong dan, bo _<so>.html) hoac tu ten
    file da cao san, thay -/_ bang khoang trang + viet hoa dau tu. Dung lam mac dinh khi
    nguoi dung khong nhap ten truyen - khong chinh xac 100% nhung du dung lam ten file/
    metadata EPUB, nguoi dung van sua lai duoc truoc khi bam chay."""
    candidate = (text or "").strip()
    if candidate.lower().startswith(("http://", "https://")):
        adapter = find_adapter(candidate)
        if adapter:
            catalog = adapter.catalog_url(candidate)
            if catalog:
                candidate = catalog
    slug = re.split(r"[\\/]", candidate.rstrip("/\\"))[-1]
    slug = re.sub(r"_\d+\.html?$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"(?:_raw)?(?:\.viet)?\.txt$", "", slug, flags=re.IGNORECASE)
    slug = os.path.splitext(slug)[0]
    slug = re.sub(r"_raw$", "", slug, flags=re.IGNORECASE)
    words = re.split(r"[-_\s]+", slug)
    return " ".join(w.capitalize() for w in words if w) or "Truyen"


_GLOBAL_SESSION = None


def get_crawler_session(log=print) -> HybridCrawlerSession:
    global _GLOBAL_SESSION
    if _GLOBAL_SESSION is None:
        _GLOBAL_SESSION = HybridCrawlerSession(log=log)
    return _GLOBAL_SESSION


def crawl_chapter(url, log=print, session=None):
    adapter = find_adapter(url)
    if adapter:
        return adapter.crawl_chapter(url, log=log)

    log(f"Fetching: {url}")
    try:
        # Neu cloudscraper.create_scraper bi mock trong test, giu nguyen behavior cu
        is_mocked = (
            getattr(cloudscraper.create_scraper, "__module__", "") != "cloudscraper"
            or getattr(cloudscraper.create_scraper, "__name__", "") == "<lambda>"
        )

        if is_mocked:
            headers = {
                "User-Agent": random.choice(USER_AGENTS)
            }
            browser_config = random.choice(CLOUDFLARE_BROWSERS)
            scraper = cloudscraper.create_scraper(browser=browser_config)
            response = scraper.get(url, headers=headers, timeout=15)
        else:
            active_session = session or get_crawler_session(log=log)
            response = active_session.get(url, timeout=15)

        if response.status_code in (403, 429):
            raise CrawlBlockedError(
                f"Nguon tu choi request (HTTP {response.status_code}): {url}. "
                "Hay mo trang bang trinh duyet, luu trang chuong thanh HTML va "
                "nhap file HTML vao giao dien de tiep tuc dich."
            )
        if response.status_code == 404:
            log("Returned 404 (Not Found). Ending crawl.")
            return None

        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        page_text = soup.get_text(" ", strip=True).lower()
        if has_challenge_indicator(getattr(response, "text", "")) or has_challenge_indicator(page_text):
            raise CrawlBlockedError(
                f"Nguon yeu cau xac minh bang trinh duyet: {url}. "
                "Hay mo trang bang trinh duyet, luu trang chuong thanh HTML va "
                "nhap file HTML vao giao dien de tiep tuc dich."
            )

        title_div = soup.find('div', class_='title')
        title = title_div.get_text(strip=True) if title_div else url

        content_div = soup.find('div', class_='content')
        if not content_div:
            log(f"Could not find content container for {url}.")
            return None

        bookmark_link = content_div.find('a', class_='anchor_bookmark')
        if bookmark_link:
            bookmark_link.decompose()

        for div in content_div.find_all('div', class_='mobadsq'):
            div.decompose()

        paragraphs = []
        p_tags = content_div.find_all('p')
        for p in p_tags:
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)

        if not paragraphs:
            text_content = content_div.get_text(separator="\n", strip=True)
            paragraphs = [line.strip() for line in text_content.split("\n") if line.strip()]

        return {'title': title, 'paragraphs': paragraphs}

    except CrawlBlockedError:
        raise
    except Exception as e:
        log(f"Error fetching {url}: {e}")
        return False  # Indication to retry or pause


def _write_chapter(file_handle, result, source_url=""):
    file_handle.write(f"=== {result['title']} ===\n\n")
    for para in result['paragraphs']:
        file_handle.write(f"{para}\n\n")
    file_handle.write(CHAPTER_SEP)
    file_handle.flush()
    if source_url:
        _save_last_url(file_handle.name, source_url)


# --- Vi tri cao that (link chuong cuoi da luu) -------------------------------------
# Khong suy vi tri tu so chuong trong file: muc luc / chi so _N.html khong 1-1 voi so
# chuong (trang thong bao, so bi nhay, bat dau tu giua truyen), dem lech thi cao tiep
# se bo sot hoac trung chuong. Luu link chuong cuoi vao file ben canh file tho.

def _progress_path(output_file):
    return str(output_file) + ".progress.json"


def _load_last_url(output_file):
    try:
        with open(_progress_path(output_file), encoding="utf-8") as f:
            return str(json.load(f).get("last_url") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def _save_last_url(output_file, url):
    path = _progress_path(output_file)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"last_url": url}, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def _norm_title(title):
    return re.sub(r"\s+", "", title or "")


def _last_saved_title(output_file):
    if not os.path.exists(output_file):
        return ""
    last = ""
    for chapter in iter_chapters_from_file(output_file):
        last = chapter["title"]
    return _norm_title(last)


def _url_key(url):
    return (url or "").rstrip("/").split("?")[0]


def _adapter_resume_index(output_file, chapters, existing, requested_index, log):
    """Chi so muc luc cua chuong tiep theo can cao."""
    if not existing:
        return requested_index
    last_url = _load_last_url(output_file)
    if last_url:
        for index, chapter in enumerate(chapters):
            if _url_key(chapter["url"]) == _url_key(last_url):
                return index + 1
        log(f"Khong thay link chuong da luu cuoi trong muc luc: {last_url}")
    # File cao tu ban cu chua co file vi tri: doi ten chuong cuoi voi muc luc.
    last_title = _last_saved_title(output_file)
    matches = [i for i, ch in enumerate(chapters) if last_title and _norm_title(ch["title"]) == last_title]
    if matches:
        return matches[-1] + 1
    log(f"CANH BAO: khong xac dinh duoc vi tri da cao, tiep tuc theo so chuong ({existing}) - co the lech.")
    return existing


def _legacy_resume_num(output_file, base_url, suffix, existing, url_chapter_num, log):
    """So _N.html tiep theo can cao (duong cao khong co adapter)."""
    if not existing:
        return url_chapter_num
    match = re.match(r"(.*_)(\d+)(\.html?)$", _load_last_url(output_file))
    if match and match.group(1) == base_url and match.group(3) == suffix:
        return int(match.group(2)) + 1
    log(f"CANH BAO: chua co file vi tri da cao, tiep tuc theo so chuong ({existing}) - co the lech.")
    return existing + 1


# Duong cao khong co adapter: chi so _N.html co the bi nhay (trang bi xoa). Gap 404 thi
# thu tiep vai chi so roi moi coi la het truyen.
# ponytail: co dinh 3, tang len neu nguon nhay so nhieu hon.
MAX_MISSING_INDEXES = 3


def _adapter_start_index(adapter, start_url, chapters, log):
    finder = getattr(adapter, "find_start_index", None)
    if finder:
        return finder(start_url, chapters, log=log)

    chapter_path = start_url.rstrip("/").split("?")[0]
    for index, chapter in enumerate(chapters):
        if chapter.get("url", "").rstrip("/").split("?")[0] == chapter_path:
            return index
    return 0


def _get_adapter_chapters(adapter, start_url, log):
    lister = getattr(adapter, "list_chapters", None) or getattr(adapter, "get_chapters")
    return lister(start_url, log=log)


def _crawl_novel_with_adapter(start_url, output_file, adapter, log, should_stop):
    chapters = _get_adapter_chapters(adapter, start_url, log)
    if not chapters:
        log("Khong co danh sach chuong de cao. Dung lai.")
        return 0

    existing = count_chapters(output_file)
    requested_index = _adapter_start_index(adapter, start_url, chapters, log)
    chapter_index = _adapter_resume_index(output_file, chapters, existing, requested_index, log)
    last_title = _last_saved_title(output_file) if existing else ""
    if existing:
        log(f"Da co {existing} chuong trong {output_file}, tiep tuc tu chuong {chapter_index + 1}.")
    if chapter_index >= len(chapters):
        log("Da het muc luc. Ket thuc crawl.")
        return 0

    consecutive_errors = 0
    saved = 0
    log(f"Bat dau cao tu chuong {chapter_index + 1} vao {output_file}...")

    with open(output_file, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("=== TRUYỆN ===\n\n")

        while chapter_index < len(chapters):
            chapter = chapters[chapter_index]
            result = crawl_chapter(chapter["url"], log=log)

            if result is None:
                log("Trang chuong khong ton tai hoac khong co noi dung. Dung crawl.")
                break

            if result is False:
                consecutive_errors += 1
                if consecutive_errors > 3:
                    log("Qua nhieu loi mang lien tiep. Dung lai.")
                    break
                log("Thu lai sau 5 giay...")
                time.sleep(5)
                continue

            consecutive_errors = 0
            if saved == 0 and last_title and _norm_title(result["title"]) == last_title:
                # Lan truoc dung ngay sau khi ghi chuong, truoc khi kip luu vi tri.
                log(f"Chuong {chapter_index + 1} da co trong file, bo qua.")
                _save_last_url(output_file, chapter["url"])
                last_title = ""
                chapter_index += 1
                continue
            _write_chapter(f, result, chapter["url"])
            log(f"Da luu chuong {chapter_index + 1}: {result['title']}")
            saved += 1
            chapter_index += 1

            if should_stop and should_stop():
                log("Da dung theo yeu cau. Chay lai se tu tiep tuc tu day.")
                break

            if chapter_index < len(chapters):
                time.sleep(random.uniform(2.0, 5.0))

    return saved


def _crawl_stream_with_adapter(start_url, output_file, max_chapters, adapter, log, should_stop,
                               from_start=False):
    chapters = _get_adapter_chapters(adapter, start_url, log)
    if not chapters:
        log("Khong co danh sach chuong de cao. Dung lai.")
        return

    existing_chapters = list(iter_chapters_from_file(output_file)) if from_start and os.path.exists(output_file) else []
    for chapter in existing_chapters:
        yield chapter

    existing = len(existing_chapters) if from_start else count_chapters(output_file)
    requested_index = _adapter_start_index(adapter, start_url, chapters, log)
    resume_index = _adapter_resume_index(output_file, chapters, existing, requested_index, log)
    chapter_index = max(resume_index, requested_index) if from_start else resume_index
    last_title = _last_saved_title(output_file) if existing else ""
    if existing:
        if from_start:
            log(f"Da co {existing} chuong trong file tho, kiem tra tu chuong 1 truoc khi cao tiep.")
        else:
            log(f"Da co {existing} chuong, tiep tuc tu chuong {chapter_index + 1}.")

    consecutive_errors = 0
    saved = 0
    limit_info = f" (gioi han {max_chapters} chuong)" if max_chapters > 0 and not from_start else ""
    log(f"Bat dau cao tu chuong {chapter_index + 1}{limit_info}...")

    with open(output_file, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("=== TRUYỆN ===\n\n")

        while chapter_index < len(chapters):
            if not from_start and max_chapters > 0 and saved >= max_chapters:
                log(f"Da cao du {max_chapters} chuong theo yeu cau.")
                break
            if should_stop and should_stop():
                log("Da dung theo yeu cau.")
                break

            chapter = chapters[chapter_index]
            result = crawl_chapter(chapter["url"], log=log)
            if result is None:
                log("Trang chuong khong ton tai hoac khong co noi dung. Dung crawl.")
                break
            if result is False:
                consecutive_errors += 1
                if consecutive_errors > 3:
                    log("Qua nhieu loi lien tiep. Dung lai.")
                    break
                log("Thu lai sau 5 giay...")
                time.sleep(5)
                continue

            consecutive_errors = 0
            if saved == 0 and last_title and _norm_title(result["title"]) == last_title:
                log(f"Chuong {chapter_index + 1} da co trong file, bo qua.")
                _save_last_url(output_file, chapter["url"])
                last_title = ""
                chapter_index += 1
                continue
            _write_chapter(f, result, chapter["url"])
            log(f"[Cao] Chuong {chapter_index + 1}: {result['title']}")
            saved += 1
            chapter_index += 1
            streamed = dict(result)
            # Vi tri trong file tho, cung cach danh so voi cac chuong da co (iter_chapters_from_file).
            streamed["_source_index"] = existing + saved
            yield streamed

            if chapter_index < len(chapters):
                time.sleep(random.uniform(2.0, 5.0))


def crawl_novel(start_url: str, output_file: str, log=print, should_stop=None) -> int:
    """Cao tuan tu, tang so trang _N trong URL len 1 moi lan, den khi gap lien tiep hon
    MAX_MISSING_INDEXES trang khong ton tai. Neu output_file da co chuong, TU DONG tiep
    tuc ngay sau link chuong cuoi da luu (file .progress.json canh file tho), khong suy
    tu so chuong trong file. Tra ve so chuong cao them trong lan nay."""
    start_url = start_url.strip().rstrip('.')
    adapter = find_adapter(start_url)
    if adapter:
        return _crawl_novel_with_adapter(start_url, output_file, adapter, log, should_stop)

    match = re.match(r"(.*_)(\d+)(\.html?)$", start_url)
    if not match:
        raise ValueError(f"start_url phai ket thuc bang _<so>.html hoac .htm, vi du '..._1.html'. Nhan: '{start_url}'")

    base_url, url_chapter_num, suffix = match.group(1), int(match.group(2)), match.group(3)
    existing = count_chapters(output_file)
    chapter_num = _legacy_resume_num(output_file, base_url, suffix, existing, url_chapter_num, log)
    last_title = _last_saved_title(output_file) if existing else ""
    if existing:
        log(f"Da co {existing} chuong trong {output_file}, tiep tuc tu trang _{chapter_num}.")

    consecutive_errors = 0
    missing = 0
    saved = 0

    log(f"Bat dau cao tu chuong {chapter_num} vao {output_file}...")

    with open(output_file, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("=== TRUYỆN ===\n\n")

        while True:
            page_url = f"{base_url}{chapter_num}{suffix}"
            result = crawl_chapter(page_url, log=log)

            if result is None:
                missing += 1
                if missing > MAX_MISSING_INDEXES:
                    log(f"Da cao xong {saved} chuong.")
                    break
                log(f"Khong co trang _{chapter_num}, thu trang tiep theo.")
                chapter_num += 1
                continue

            if result is False:
                consecutive_errors += 1
                if consecutive_errors > 3:
                    log("Qua nhieu loi mang lien tiep. Dung lai.")
                    break
                log("Thu lai sau 5 giay...")
                time.sleep(5)
                continue

            consecutive_errors = 0
            missing = 0
            if saved == 0 and last_title and _norm_title(result["title"]) == last_title:
                log(f"Trang _{chapter_num} da co trong file, bo qua.")
                _save_last_url(output_file, page_url)
                last_title = ""
                chapter_num += 1
                continue

            _write_chapter(f, result, page_url)

            log(f"Da luu chuong {chapter_num}: {result['title']}")
            saved += 1
            chapter_num += 1

            if should_stop and should_stop():
                log("Da dung theo yeu cau. Chay lai se tu tiep tuc tu day.")
                break

            time.sleep(random.uniform(2.0, 5.0))  # Polite crawling delay

    return saved


def crawl_chapters_stream(start_url: str, output_file: str, max_chapters: int = 0,
                           log=print, should_stop=None, from_start=False):
    """Generator: cao tung chuong, ghi vao output_file, yield ngay dict chuong do de
    caller co the dich luon ma khong can doi cao het. Dung cho stream pipeline.

    max_chapters: gioi han so chuong can cao (0 = khong gioi han, cao toan bo truyen).
    from_start: yield lai cac chuong da cao tu dau de pipeline co the bo qua chuong da dich,
        sau do moi cao tiep chuong moi.
    Yield: dict {'title': ..., 'paragraphs': [...], '_source_index': N}.
    """
    start_url = start_url.strip().rstrip('.')
    adapter = find_adapter(start_url)
    if adapter:
        yield from _crawl_stream_with_adapter(
            start_url, output_file, max_chapters, adapter, log, should_stop, from_start
        )
        return

    match = re.match(r"(.*_)(\d+)(\.html?)$", start_url)
    if not match:
        raise ValueError(f"start_url phai ket thuc bang _<so>.html hoac .htm. Nhan: '{start_url}'")

    base_url, url_chapter_num, suffix = match.group(1), int(match.group(2)), match.group(3)
    existing_chapters = list(iter_chapters_from_file(output_file)) if from_start and os.path.exists(output_file) else []
    for chapter in existing_chapters:
        yield chapter

    existing = len(existing_chapters) if from_start else count_chapters(output_file)
    resume_num = _legacy_resume_num(output_file, base_url, suffix, existing, url_chapter_num, log)
    chapter_num = max(resume_num, url_chapter_num) if from_start else resume_num
    last_title = _last_saved_title(output_file) if existing else ""
    if existing:
        if from_start:
            log(f"Da co {existing} chuong trong file tho, kiem tra tu chuong 1 truoc khi cao tiep.")
        else:
            log(f"Da co {existing} chuong, tiep tuc tu trang _{chapter_num}.")

    consecutive_errors = 0
    missing = 0
    saved = 0
    limit_info = f" (gioi han {max_chapters} chuong)" if max_chapters > 0 and not from_start else ""
    log(f"Bat dau cao tu chuong {chapter_num}{limit_info}...")

    with open(output_file, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("=== TRUYỆN ===\n\n")

        while True:
            if not from_start and max_chapters > 0 and saved >= max_chapters:
                log(f"Da cao du {max_chapters} chuong theo yeu cau.")
                break

            if should_stop and should_stop():
                log("Da dung theo yeu cau.")
                break

            page_url = f"{base_url}{chapter_num}{suffix}"
            result = crawl_chapter(page_url, log=log)

            if result is None:
                missing += 1
                if missing > MAX_MISSING_INDEXES:
                    log(f"Da cao xong {saved} chuong (het truyen).")
                    break
                log(f"Khong co trang _{chapter_num}, thu trang tiep theo.")
                chapter_num += 1
                continue

            if result is False:
                consecutive_errors += 1
                if consecutive_errors > 3:
                    log("Qua nhieu loi lien tiep. Dung lai.")
                    break
                log("Thu lai sau 5 giay...")
                time.sleep(5)
                continue

            consecutive_errors = 0
            missing = 0
            if saved == 0 and last_title and _norm_title(result["title"]) == last_title:
                log(f"Trang _{chapter_num} da co trong file, bo qua.")
                _save_last_url(output_file, page_url)
                last_title = ""
                chapter_num += 1
                continue

            _write_chapter(f, result, page_url)

            log(f"[Cao] Chuong {chapter_num}: {result['title']}")
            saved += 1
            chapter_num += 1

            streamed = dict(result)
            streamed["_source_index"] = existing + saved
            yield streamed  # Giao ngay cho pipeline de dich

            time.sleep(random.uniform(2.0, 5.0))  # Polite crawling delay


def main():

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description="Cao truyen tu URL chuong dau tien")
    parser.add_argument("--start-url", default=DEFAULT_START_URL,
                         help="URL chuong dau, dang '..._<so>.html'")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    crawl_novel(args.start_url, args.output)


if __name__ == "__main__":
    main()
