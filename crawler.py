import argparse
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

DEFAULT_START_URL = "https://www.wa01.com/novel/pagea/disanchongrenge-changshuxin_1.html"
DEFAULT_OUTPUT = "truyen_de_tam_trung_nhan_cach.txt"
CHAPTER_SEP = "\n" + "=" * 40 + "\n\n"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


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


def count_chapters(file_path: str) -> int:
    """Dem so chuong da hoan tat trong 1 file dinh dang === ... === (ca file tho da cao
    lan file da dich deu dung chung dinh dang nay) - dung "="*40 lam moc ket thuc 1
    chuong vi dong nay chi xuat hien khi 1 chuong da ghi xong hoan toan."""
    if not os.path.exists(file_path):
        return 0
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().count("=" * 40)


def guess_title(text: str) -> str:
    """Doan ten truyen tu URL chuong 1 (slug cuoi duong dan, bo _<so>.html) hoac tu ten
    file da cao san, thay -/_ bang khoang trang + viet hoa dau tu. Dung lam mac dinh khi
    nguoi dung khong nhap ten truyen - khong chinh xac 100% nhung du dung lam ten file/
    metadata EPUB, nguoi dung van sua lai duoc truoc khi bam chay."""
    slug = text.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"_\d+\.html?$", "", slug)
    slug = os.path.splitext(slug)[0]
    words = re.split(r"[-_]+", slug)
    return " ".join(w.capitalize() for w in words if w) or "Truyen"


def crawl_chapter(url, log=print):
    log(f"Fetching: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 404:
            log("Returned 404 (Not Found). Ending crawl.")
            return None

        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

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

    except requests.exceptions.RequestException as e:
        log(f"Error fetching {url}: {e}")
        return False  # Indication to retry or pause


def crawl_novel(start_url: str, output_file: str, log=print, should_stop=None) -> int:
    """Cao tuan tu tu chuong dau con thieu, tang so chuong trong URL len 1 moi lan, den
    khi gap 404. Neu output_file da co san N chuong (vd chay lan truoc bi dung giua
    chung), TU DONG tiep tuc tu chuong N+1 bat ke so chuong ghi trong start_url - chi
    dung start_url de suy ra mau URL (base_url/suffix), khong dung de xac dinh diem
    bat dau, tranh cao trung lap khi resume. Tra ve so chuong cao them trong lan nay."""
    match = re.match(r"(.*_)(\d+)(\.html)$", start_url)
    if not match:
        raise ValueError(f"start_url phai ket thuc bang _<so>.html, vi du '..._1.html'. Nhan: {start_url}")

    base_url, url_chapter_num, suffix = match.group(1), int(match.group(2)), match.group(3)
    existing = count_chapters(output_file)
    chapter_num = existing + 1 if existing else url_chapter_num
    if existing:
        log(f"Da co {existing} chuong trong {output_file}, tiep tuc tu chuong {chapter_num}.")

    consecutive_errors = 0
    saved = 0

    log(f"Bat dau cao tu chuong {chapter_num} vao {output_file}...")

    with open(output_file, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("=== TRUYỆN ===\n\n")

        while True:
            result = crawl_chapter(f"{base_url}{chapter_num}{suffix}", log=log)

            if result is None:
                log(f"Da cao xong {saved} chuong.")
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

            f.write(f"=== {result['title']} ===\n\n")
            for para in result['paragraphs']:
                f.write(f"{para}\n\n")
            f.write(CHAPTER_SEP)
            f.flush()

            log(f"Da luu chuong {chapter_num}: {result['title']}")
            saved += 1
            chapter_num += 1

            if should_stop and should_stop():
                log("Da dung theo yeu cau. Chay lai se tu tiep tuc tu day.")
                break

            time.sleep(1)  # Polite crawling delay

    return saved


def crawl_chapters_stream(start_url: str, output_file: str, max_chapters: int = 0,
                           log=print, should_stop=None):
    """Generator: cao tung chuong, ghi vao output_file, yield ngay dict chuong do de
    caller co the dich luon ma khong can doi cao het. Dung cho stream pipeline.

    max_chapters: gioi han so chuong can cao (0 = khong gioi han, cao toan bo truyen).
    Yield: dict {'title': ..., 'paragraphs': [...]} sau moi chuong cao thanh cong.
    """
    match = re.match(r"(.*_)(\d+)(\.html)$", start_url)
    if not match:
        raise ValueError(f"start_url phai ket thuc bang _<so>.html. Nhan: {start_url}")

    base_url, url_chapter_num, suffix = match.group(1), int(match.group(2)), match.group(3)
    existing = count_chapters(output_file)
    chapter_num = existing + 1 if existing else url_chapter_num
    if existing:
        log(f"Da co {existing} chuong, tiep tuc tu chuong {chapter_num}.")

    consecutive_errors = 0
    saved = 0
    limit_info = f" (gioi han {max_chapters} chuong)" if max_chapters > 0 else ""
    log(f"Bat dau cao tu chuong {chapter_num}{limit_info}...")

    with open(output_file, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("=== TRUYỆN ===\n\n")

        while True:
            if max_chapters > 0 and saved >= max_chapters:
                log(f"Da cao du {max_chapters} chuong theo yeu cau.")
                break

            if should_stop and should_stop():
                log("Da dung theo yeu cau.")
                break

            result = crawl_chapter(f"{base_url}{chapter_num}{suffix}", log=log)

            if result is None:
                log(f"Da cao xong {saved} chuong (het truyen).")
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

            f.write(f"=== {result['title']} ===\n\n")
            for para in result['paragraphs']:
                f.write(f"{para}\n\n")
            f.write(CHAPTER_SEP)
            f.flush()

            log(f"[Cao] Chuong {chapter_num}: {result['title']}")
            saved += 1
            chapter_num += 1

            yield result  # Giao ngay cho pipeline de dich

            time.sleep(1)  # Polite crawling delay


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
