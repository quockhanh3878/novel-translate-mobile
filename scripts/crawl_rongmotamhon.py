"""Crawl Từ điển Hán Việt từ rongmotamhon.net (~55K entries).

Cơ chế (verified):
  1. Submit form `tra_van` tại URL chính để lấy danh sách entries theo âm Hán Việt
     → trả về HTML chứa list các link `tu-dien_han-viet_<slug>_rong-mo-tam-hon.html`
  2. Mở từng entry page → parse `<p class="lead">` chứa nghĩa Việt

Usage:
  python scripts/crawl_rongmotamhon.py --output dictionaries/rongmotamhon_raw.json
  python scripts/crawl_rongmotamhon.py --resume   # resume từ cache
"""

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Thiếu thư viện: {e}. Cài: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

# Force UTF-8 stdout/stderr trên Windows
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, OSError):
        pass


# ============================================================================
# Config
# ============================================================================

BASE_URL = "https://rongmotamhon.net"
ENTRY_LIST_URL = f"{BASE_URL}/tu-dien_han-viet_none_rong-mo-tam-hon.html"
ENTRY_URL_PREFIX = f"{BASE_URL}/tu-dien_han-viet_"

# Danh sách các âm đầu (Hán Việt) - đủ để cover ~99% entries
SYLLABLES = [
    "a", "ai", "am", "an", "ang", "anh", "ao", "au", "ay",
    "ba", "bai", "ban", "bang", "bap", "bat", "bay", "be", "ben", "beng", "bi", "bia", "bich", "bien", "biet",
    "bin", "binh", "bip", "bit", "bo", "boc", "boi", "bom", "bon", "bong", "bop", "bot", "bu", "bua",
    "buc", "bui", "bung", "buoc", "buoi", "buom", "buon", "buong", "buot", "but", "buu",
    "ca", "cai", "cam", "can", "cang", "canh", "cao", "cap", "cat", "cau", "cay", "ce",
    "cha", "chai", "cham", "chan", "chang", "chanh", "chao", "chap", "chat", "chau", "chay", "che",
    "chi", "chia", "chich", "chien", "chiet", "chin", "chinh", "chip", "cho", "choang", "choi",
    "chon", "chong", "chop", "chot", "chu", "chua", "chuc", "chui", "chung", "chuo", "chuoc",
    "chuoi", "chuong", "chup", "chut", "chuy", "co", "coi", "com", "con", "cong", "cop", "cot",
    "cu", "cua", "cuc", "cui", "cung", "cuoc", "cuoi", "cuom", "cuon", "cuong", "cup", "cut",
    "cuu", "da", "dai", "dam", "dan", "dang", "danh", "dao", "dap", "dat", "dau", "day",
    "de", "di", "dia", "dich", "dien", "diet", "diều", "din", "dinh", "do", "doc", "doi",
    "don", "dong", "dop", "dot", "du", "dua", "duc", "dui", "dum", "dun", "dung", "duoc",
    "duoi", "duong", "dup", "dut", "duy", "da", "e", "em", "en", "eng", "eo", "eu",
    "ga", "gai", "gam", "gan", "gang", "ganh", "gao", "gap", "gay", "gi", "gia", "giac",
    "giai", "giam", "gian", "giang", "giao", "giap", "giat", "giau", "giay", "gich",
    "gien", "giet", "gin", "giong", "gip", "go", "goc", "goi", "gom", "gon", "gong",
    "got", "gu", "gua", "guc", "gui", "gung", "guoc", "guom", "guong", "gup",
    "ha", "hai", "ham", "han", "hang", "hanh", "hao", "hap", "hat", "hau", "hay",
    "he", "hi", "hiem", "hien", "hiep", "hiet", "hin", "hinh", "hit",
    "ho", "hoa", "hoach", "hoai", "hoam", "hoan", "hoang", "hoanh", "hoc", "hoi",
    "hom", "hon", "hong", "hop", "hot", "hu", "hua", "huc", "hue", "hui", "hum",
    "hun", "hung", "huong", "hup", "hut", "huy", "huy", "huych", "huyen", "huynh",
    "i", "iа", "ích", "im", "in", "inh", "ip", "it", "iu",
    "ka", "kha", "khi", "kho", "khu", "ki", "ky", "ke", "kiem", "khoa", "khai", "khan", "khe",
    "la", "lac", "lai", "lam", "lan", "lang", "lanh", "lao", "lap", "lat", "lau",
    "lay", "le", "lem", "len", "leo", "lep", "li", "lia", "lich", "lien", "liet",
    "lin", "linh", "lip", "lit", "lo", "loc", "loi", "lon", "long", "lop", "lot",
    "lu", "lua", "luc", "lui", "lum", "lun", "lung", "luoc", "luoi", "luom",
    "luon", "luong", "lup", "lut", "luy", "luy", "ly",
    "ma", "mac", "mai", "mam", "man", "mang", "manh", "mao", "map", "mat", "mau", "may",
    "me", "mec", "mi", "mich", "mien", "miet", "min", "minh", "mit", "mo", "moc", "moi",
    "mom", "mon", "mong", "mot", "mu", "mua", "muc", "mui", "mung", "muoi", "muom",
    "muon", "muong", "mup", "mut", "muy", "my", "na", "nai", "nam", "nan", "nang",
    "nanh", "nao", "nap", "nat", "nay", "ne", "nem", "neo", "nep", "nga", "ngac",
    "ngai", "ngam", "ngan", "ngang", "nganh", "ngao", "ngap", "ngat", "ngau", "ngay",
    "nghe", "nghi", "nghia", "nghich", "nghien", "nghiet", "nghin", "nghinh", "ngo",
    "ngoa", "ngoac", "ngoai", "ngoan", "ngoang", "ngoc", "ngoi", "ngom", "ngon", "ngong",
    "ngop", "ngot", "ngu", "nguc", "ngui", "ngung", "nguoc", "nguoi", "nguong", "ngup",
    "ngut", "nguy", "nguyen", "nguynh", "nha", "nhac", "nhai", "nham", "nhan", "nhang",
    "nhanh", "nhao", "nhap", "nhat", "nhau", "nhay", "nhe", "nhi", "nhia", "nhich",
    "nhien", "nhiet", "nhim", "nhin", "nhip", "nhit", "nho", "nhoc", "nhoi", "nhom",
    "nhon", "nhong", "nhop", "nhot", "nhu", "nhuc", "nhue", "nhung", "nhuoc", "nhuoi",
    "nhuom", "nhuong", "nhut", "nhuy", "o", "oc", "oi", "om", "on", "ong", "op", "ot",
    "pa", "pho", "phu", "pha", "phi", "pho", "phu", "phai", "pham", "phan", "phang",
    "phap", "phat", "phau", "phay", "phe", "phi", "phia", "phich", "phien", "phiet",
    "phin", "phinh", "pho", "phoc", "phoi", "phom", "phon", "phong", "phot", "phu",
    "phuc", "phui", "phum", "phun", "phung", "phuoc", "phuoi", "phuon", "phuong",
    "phup", "phut", "phuy", "qua", "quac", "quai", "quam", "quan", "quang", "quanh",
    "quao", "quap", "quat", "quay", "que", "qui", "quoc", "quoi", "quon", "quong",
    "quy", "quyen", "quynh", "ra", "rac", "rai", "ram", "ran", "rang", "ranh", "rao",
    "rap", "rat", "rau", "ray", "re", "rem", "ren", "reo", "ri", "ria", "rich", "rien",
    "riet", "rim", "rin", "rinh", "rip", "rit", "ro", "roc", "roi", "rom", "ron",
    "rong", "rop", "rot", "ru", "ruc", "rui", "rum", "run", "rung", "ruoc", "ruoi",
    "ruom", "ruon", "ruong", "rut", "ruy", "sa", "sac", "sai", "sam", "san", "sang",
    "sanh", "sao", "sap", "sat", "sau", "say", "se", "si", "sia", "sich", "sien",
    "siet", "sin", "sinh", "sip", "so", "soc", "soi", "som", "son", "song", "sop",
    "sot", "su", "sua", "suc", "sui", "sum", "sun", "sung", "suoc", "suoi", "suom",
    "suon", "suong", "sup", "sut", "suy", "ta", "tac", "tai", "tam", "tan", "tang",
    "tanh", "tao", "tap", "tat", "tau", "tay", "te", "tem", "ten", "teo", "ti", "tia",
    "tich", "tien", "tiet", "tin", "tinh", "tip", "tit", "to", "toc", "toi", "tom",
    "ton", "tong", "top", "tot", "tu", "tua", "tuc", "tui", "tum", "tun", "tung",
    "tuoc", "tuoi", "tuom", "tuon", "tuong", "tup", "tut", "tuy", "tuyen", "ty",
    "ua", "uc", "ui", "um", "un", "ung", "uoc", "uoi", "uom", "uong", "up", "ut",
    "uy", "uy", "va", "vai", "vam", "van", "vang", "vanh", "vao", "vap", "vat",
    "vau", "vay", "ve", "vi", "via", "vich", "vien", "viet", "vin", "vinh", "vit",
    "vo", "voc", "voi", "vom", "von", "vong", "vot", "vu", "vuc", "vui", "vun",
    "vung", "vuoc", "vuoi", "vuon", "vuong", "vut", "xa", "xac", "xai", "xam", "xan",
    "xang", "xanh", "xao", "xap", "xat", "xau", "xay", "xe", "xi", "xia", "xich",
    "xien", "xiet", "xin", "xinh", "xo", "xoc", "xoi", "xon", "xong", "xop", "xot",
    "xu", "xuc", "xui", "xum", "xun", "xung", "xuoc", "xuoi", "xuong", "xup", "xut",
    "y", "ya", "yem", "yen", "yet", "yeu", "yên", "yết", "yêu",
    "za", "zac", "zai", "zam", "zan", "zang", "zanh", "zao", "zap", "zat", "zau",
    "ze", "zi", "zia", "zich", "zien", "ziet", "zin", "zinh", "zo", "zoc", "zoi",
    "zon", "zong", "zot", "zu", "zuc", "zui", "zum", "zun", "zung", "zuoc", "zuoi",
    "zuom", "zuon", "zuong", "zup", "zut",
]


# ============================================================================
# Crawler
# ============================================================================

class RongMoTamHonCrawler:
    def __init__(self, output_path: Path, delay: float = 1.5, max_retries: int = 3):
        self.output_path = output_path
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            "Referer": ENTRY_LIST_URL,
        })
        # Cache: slugs đã fetch
        self.entries: Dict[str, str] = {}
        self.visited_slugs: Set[str] = set()
        if output_path.exists():
            try:
                with output_path.open("r", encoding="utf-8") as f:
                    self.entries = json.load(f)
                self.visited_slugs = set(self.entries.keys())
                print(f"[RESUME] Đã có {len(self.entries):,} entries trong cache", file=sys.stderr)
            except (json.JSONDecodeError, OSError):
                pass

    def fetch(self, url: str, method: str = "GET", data: Optional[dict] = None) -> Optional[str]:
        for attempt in range(1, self.max_retries + 1):
            try:
                if method == "POST":
                    r = self.session.post(url, data=data, timeout=30)
                else:
                    r = self.session.get(url, timeout=30)
                r.raise_for_status()
                # Fix encoding nếu server trả về charset sai
                if r.encoding and r.encoding.lower() != "utf-8":
                    r.encoding = "utf-8"
                return r.text
            except requests.RequestException as e:
                wait = 2 ** attempt
                print(f"  [RETRY] {method} {url} attempt {attempt}: {e}", file=sys.stderr)
                if attempt < self.max_retries:
                    time.sleep(wait)
        return None

    def get_entry_slugs(self, syllable: str) -> List[str]:
        """Submit form tra_van với âm Hán Việt → lấy list entry slugs."""
        html = self.fetch(
            ENTRY_LIST_URL,
            method="POST",
            data={"tra_van": syllable, "submit2": "Tra vần"},
        )
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        # Tìm list entries: link có href dạng tu-dien_han-viet_<slug>_rong-mo-tam-hon.html
        slugs: Set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if not isinstance(href, str):
                continue
            m = re.match(r"^tu-dien_han-viet_(\w+)_rong-mo-tam-hon\.html", href)
            if m:
                slug = m.group(1)
                if slug != "none" and slug not in ("lgddsssc",):  # bỏ placeholder
                    slugs.add(slug)
        return sorted(slugs)

    def fetch_entry(self, slug: str) -> Optional[str]:
        """Mở page entry, parse nghĩa Việt từ <p class='lead'>."""
        url = f"{ENTRY_URL_PREFIX}{slug}_rong-mo-tam-hon.html"
        html = self.fetch(url, method="GET")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        # Tìm breadcrumb để lấy Hán tự + âm Hán Việt: "Đang xem mục từ: can - 乾（幹）"
        # JSON-LD BreadcrumbList có dạng: "name": "Đang xem mục từ: can dự - 干預"
        # → phải dùng regex cẩn thận
        hanviet_chinese = ""
        # Tìm trong JSON-LD schema.org BreadcrumbList (item.name)
        for script in soup.find_all("script", type="application/ld+json"):
            text = script.string or ""
            m = re.search(r'"name"\s*:\s*"Đang xem mục từ:\s*([^"]+)"', text)
            if m:
                hanviet_chinese = m.group(1).strip()
                break
        # Fallback: tìm trong breadcrumb HTML
        if not hanviet_chinese:
            breadcrumb_el = soup.find(string=re.compile(r"Đang xem mục từ:"))
            if breadcrumb_el:
                m = re.search(r"Đang xem mục từ:\s*([^»\"]+)", breadcrumb_el)
                if m:
                    hanviet_chinese = m.group(1).strip()

        # Tìm <p class="lead"> chứa nghĩa Việt
        lead = soup.find("p", class_="lead")
        if not lead:
            return None
        meaning = lead.get_text(separator=" ", strip=True)
        # Loại bỏ credit "(Từ điển ...)" ở cuối
        meaning = re.sub(r"\s*\([^)]*Từ điển[^)]*\)\s*$", "", meaning).strip()
        if not meaning:
            return None
        # Lưu với key là phần Hán tự (chinese)
        # breadcrumb: "can - 乾（幹）" → split lấy chinese
        if " - " in hanviet_chinese:
            chinese = hanviet_chinese.split(" - ", 1)[1].strip()
        else:
            chinese = hanviet_chinese
        if chinese and meaning:
            self.entries[chinese] = meaning
            return meaning
        return None

    def crawl_syllable(self, syllable: str) -> int:
        """Crawl tất cả entries cho 1 âm Hán Việt."""
        slugs = self.get_entry_slugs(syllable)
        new_count = 0
        for slug in slugs:
            if slug in self.visited_slugs:
                continue
            time.sleep(self.delay)
            meaning = self.fetch_entry(slug)
            if meaning:
                new_count += 1
                self.visited_slugs.add(slug)
            if new_count % 20 == 0 and new_count > 0:
                self._save_cache()
                print(f"  [{syllable}] {new_count}/{len(slugs)} new, tổng {len(self.entries):,}", file=sys.stderr)
        return new_count

    def _save_cache(self) -> None:
        """Lưu cache (atomic write)."""
        tmp = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)
        tmp.replace(self.output_path)

    def crawl_all(self, syllables: List[str]) -> int:
        total_new = 0
        print(f"Bắt đầu crawl {len(syllables)} âm, delay={self.delay}s/req", file=sys.stderr)
        for i, syl in enumerate(syllables, 1):
            print(f"\n[{i}/{len(syllables)}] Crawl âm '{syl}'...", file=sys.stderr)
            new_count = self.crawl_syllable(syl)
            total_new += new_count
            print(f"  → +{new_count} mới. Tổng entries: {len(self.entries):,}", file=sys.stderr)
            self._save_cache()
        return total_new


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl Từ điển Hán Việt từ rongmotamhon.net")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(r"F:\Clone\novel-translate-mobile\dictionaries\rongmotamhon_raw.json"),
        help="File output JSON",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay giữa các request (giây) - polite scraping",
    )
    parser.add_argument(
        "--syllables",
        nargs="*",
        default=None,
        help="Danh sách âm cần crawl (mặc định: tất cả)",
    )
    parser.add_argument(
        "--max-syllables",
        type=int,
        default=0,
        help="Giới hạn số âm crawl (0 = tất cả). Dùng để test nhanh.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume từ cache file (mặc định: tự động nếu file tồn tại)",
    )
    args = parser.parse_args()

    syl_list = args.syllables if args.syllables else SYLLABLES
    if args.max_syllables > 0:
        syl_list = syl_list[: args.max_syllables]

    crawler = RongMoTamHonCrawler(
        output_path=args.output,
        delay=args.delay,
    )

    print(f"Output:  {args.output}")
    print(f"Syllables: {len(syl_list)}")
    print()

    total_new = crawler.crawl_all(syl_list)
    crawler._save_cache()

    print(f"\n{'=' * 60}")
    print(f"  TỔNG KẾT CRAWL")
    print(f"{'=' * 60}")
    print(f"  Entries mới crawl được: {total_new:,}")
    print(f"  Tổng entries trong file: {len(crawler.entries):,}")
    print(f"  File output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())