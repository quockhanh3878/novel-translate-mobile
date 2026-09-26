"""Build Hán Việt dictionaries từ nhiều nguồn miễn phí.

Nguồn data (đã clone về C:/Users/quock/AppData/Local/Temp/opencode/dict-sources/):
  1. CVDICT (CC BY-SA 4.0) - 122K từ/cụm từ Hán-Việt, format ts (CEDICT variant)
  2. hanviet-pinyin-wordlist (MIT) - ~11K chữ Hán đơn lẻ với Hán Việt + pinyin
  3. chinese-hanviet-cognates - TSV mapping cognates Trung-Việt + bonus phienam.txt, vietphrases.txt
  4. chugiai-zh-en-vi (CC BY-SA 4.0) - cvdict_full.json (CVDICT dạng JSON), cedict_full.json (CC-CEDICT Anh)
  5. hanzi-sino-vietnamese (CC BY 4.0) - 659 chữ HSK theo level với Hán Việt readings

Output:
  dictionaries/hanviet_chars.json   - {chữ Hán: [âm Hán Việt các cách đọc]}
  dictionaries/hanviet_words.json   - {cụm từ Hán: nghĩa Việt}
  dictionaries/hanviet_idioms.json  - {thành ngữ Hán: nghĩa Việt}
  glossary.json                     - MERGED với entries hiện có

Usage:
  python scripts/build_hanviet_dict.py --sources-dir <path>
"""

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Force UTF-8 stdout/stderr trên Windows (cp1252 mặc định)
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, OSError):
        pass


# ============================================================================
# Loaders cho từng nguồn
# ============================================================================

def load_cvdict_text(path: Path) -> Dict[str, str]:
    """Parse CVDICT.u8 - format ts (CEDICT variant):
        中國 中國 Trung Quốc /zhōng guó/
        學生 學生 học sinh /xué shēng/

    Format thực tế (verified):
        % % [pa1] /phần trăm (Đài Loan)/
        2019冠狀病毒病 2019冠状病毒病 [...] /COVID-19, .../

    Trả về {chữ Hán: nghĩa Việt}.
    """
    out: Dict[str, str] = {}
    if not path.exists():
        print(f"  [SKIP] Không tìm thấy {path}", file=sys.stderr)
        return out

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Format: <trad> <simp> [pinyin_with_tones] /vietnamese_meaning(s)/
            # Ví dụ: 中國 中國 [zhōng guó] /Trung Quốc/
            # Ví dụ phức tạp: 3C 3C [san1 C] /nghĩa1/nghĩa2/
            m = re.match(r"^(\S+)\s+(\S+)\s+\[[^\]]*\]\s+(/.+/)\s*$", line)
            if not m:
                continue
            trad, simp, vi_part = m.group(1), m.group(2), m.group(3)
            # Tách nghĩa Việt - phần giữa 2 dấu /
            # Strip leading/trailing /
            inner = vi_part.strip("/").strip()
            if not inner:
                continue
            # Nếu có nhiều nghĩa cách nhau bởi /, lấy nghĩa đầu tiên
            # (một số entries có dạng "nghĩa1 (chú thích)/nghĩa2/")
            meanings = [m.strip() for m in inner.split("/") if m.strip()]
            if not meanings:
                continue
            # Lấy nghĩa đầu tiên (thường là nghĩa chính)
            best = meanings[0]
            # Nếu nghĩa đầu quá ngắn (< 2 chars) và có nghĩa sau dài hơn, lấy cái dài hơn
            if len(best) < 3 and len(meanings) > 1:
                best = max(meanings, key=len)
            # Ưu tiên key là traditional (nếu khác simplified)
            key = trad if trad != simp else simp
            out[key] = best
    return out


def load_cvdict_json(path: Path) -> Dict[str, str]:
    """Parse cvdict_full.json - format dict:
        {
          "2019冠状病毒病": {
            "trad": "2019冠狀病毒病",
            "pinyin": "er4 ling2 yi1 jiu3 guan1 zhuang4 bing4 du2 bing4",
            "definition": "COVID-19, bệnh coronavirus được xác định năm 2019"
          },
          ...
        }

    Trả về {chữ Hán (simplified): nghĩa Việt}.
    """
    out: Dict[str, str] = {}
    if not path.exists():
        print(f"  [SKIP] Không tìm thấy {path}", file=sys.stderr)
        return out

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return out

    for han, entry in data.items():
        if not isinstance(entry, dict):
            continue
        definition = entry.get("definition", "")
        if not definition or not isinstance(definition, str):
            continue
        # definition đã chứa nghĩa Việt (verified)
        # Tách theo dấu ";" hoặc "/" - lấy nghĩa đầu tiên
        first_meaning = re.split(r"[;/]", definition, maxsplit=1)[0].strip()
        if first_meaning:
            # Prefer traditional nếu có
            trad = entry.get("trad")
            key = trad if trad and trad != han else han
            out[key] = first_meaning
    return out


def load_hanviet_csv(path: Path) -> Dict[str, List[str]]:
    """Parse hanviet.csv - format: char,hanviet,pinyin

    Ví dụ:
      中,['trung'],zhong1
      中,['trúng'],zhong4

    Trả về {chữ Hán: list các âm Hán Việt}.
    """
    out: Dict[str, Set[str]] = {}
    if not path.exists():
        print(f"  [SKIP] Không tìm thấy {path}", file=sys.stderr)
        return {}

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            char = row.get("char", "").strip()
            hanviet_raw = row.get("hanviet", "").strip()
            if not char or not hanviet_raw:
                continue
            # Parse list dạng ['trung'] hoặc ['trung', 'trúng']
            # Bỏ qua nếu là danh sách rỗng []
            m = re.findall(r"'([^']+)'", hanviet_raw)
            if not m:
                # Thử parse không có nháy đơn
                m = re.findall(r'"([^"]+)"', hanviet_raw)
            if not m or all(not x.strip() for x in m):
                continue
            out.setdefault(char, set()).update(x.strip() for x in m if x.strip())
    # Convert set -> sorted list (giữ thứ tự canonical: reading ngắn trước)
    return {k: sorted(v, key=lambda x: (len(x), x)) for k, v in out.items()}


def load_cognates_tsv(path: Path) -> Dict[str, str]:
    """Parse chinese-hanviet-cognates.tsv - format:
        ranking\tfreq\thanz\ttrad\tpinyin\thanviet\tmeaning
        5\t1332.15\t可以\t可以\tkeyi\tkhả đi\tcó thể/khả đi/...

    Trả về {cụm từ Hán (simplified): nghĩa Việt (lấy nghĩa đầu tiên)}.
    """
    out: Dict[str, str] = {}
    if not path.exists():
        print(f"  [SKIP] Không tìm thấy {path}", file=sys.stderr)
        return out

    with path.open("r", encoding="utf-8") as f:
        header = f.readline().strip().split("\t")
        # chinese word ranking, frequency, word, traditional, pinyin, hanviet, meaning
        try:
            word_idx = header.index("word")
            mean_idx = header.index("meaning")
        except ValueError:
            # Fallback: dùng index
            word_idx = 2
            mean_idx = 6
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) <= max(word_idx, mean_idx):
                continue
            word = cols[word_idx].strip()
            meaning = cols[mean_idx].strip()
            if not word or not meaning:
                continue
            # Lấy nghĩa đầu tiên (phân cách bởi /)
            first_meaning = meaning.split("/")[0].strip()
            if first_meaning:
                out[word] = first_meaning
    return out


def load_phienam(path: Path) -> Dict[str, List[str]]:
    """Parse phienam.txt - format: 漢=âm Hán Việt (1 chữ mỗi dòng)

    Ví dụ:
      中=trung
      中=trúng

    Trả về {chữ Hán: [âm Hán Việt các cách đọc]}.
    """
    out: Dict[str, Set[str]] = {}
    if not path.exists():
        print(f"  [SKIP] Không tìm thấy {path}", file=sys.stderr)
        return {}

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            char, hanviet = line.split("=", 1)
            char = char.strip()
            hanviet = hanviet.strip()
            if not char or not hanviet:
                continue
            out.setdefault(char, set()).add(hanviet)
    return {k: sorted(v, key=lambda x: (len(x), x)) for k, v in out.items()}


def load_vietphrases(path: Path) -> Dict[str, str]:
    """Parse vietphrases.txt - format: 中文=nghĩa Việt (cụm từ)

    Ví dụ:
      後天下之樂而樂=sau mới vui niềm vui của thiên hạ

    Trả về {cụm từ Hán: nghĩa Việt}.
    """
    out: Dict[str, str] = {}
    if not path.exists():
        print(f"  [SKIP] Không tìm thấy {path}", file=sys.stderr)
        return out

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            parts = line.split("=", 1)
            if len(parts) != 2:
                continue
            han, vi = parts[0].strip(), parts[1].strip()
            if not han or not vi:
                continue
            # Lấy nghĩa đầu tiên nếu có phân cách /
            first = vi.split("/")[0].strip()
            if first:
                out[han] = first
    return out


def load_hanzi_sino(path: Path) -> Dict[str, List[str]]:
    """Parse characters.json - format list of dict:
        [
          {
            "hanzi": "一",
            "pinyin": "yī",
            "sinoViet": "Nhất",
            "meaningVi": "một, số một",
            "hskLevel": 1,
            ...
          },
          ...
        ]

    Trả về {chữ Hán: [âm Hán Việt]}.
    """
    out: Dict[str, List[str]] = {}
    if not path.exists():
        print(f"  [SKIP] Không tìm thấy {path}", file=sys.stderr)
        return out

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return out

    for entry in data:
        if not isinstance(entry, dict):
            continue
        char = entry.get("hanzi") or entry.get("character") or entry.get("char")
        if not char:
            continue
        # Field chính là sinoViet (verified)
        sino = entry.get("sinoViet") or entry.get("sino_vietnamese") or entry.get("hanviet")
        if not sino:
            continue
        if isinstance(sino, str):
            readings_list = [r.strip() for r in re.split(r"[,/;|]", sino) if r.strip()]
        elif isinstance(sino, list):
            readings_list = [str(r).strip() for r in sino if r]
        else:
            continue
        if readings_list:
            out[char] = readings_list
    return out


# ============================================================================
# Logic merge & main
# ============================================================================

def merge_chars(target: Dict[str, List[str]], source: Dict[str, List[str]]) -> int:
    """Merge char-level readings (union). Trả về số readings mới thêm vào."""
    added = 0
    for char, readings in source.items():
        existing = set(target.get(char, []))
        for r in readings:
            if r not in existing:
                existing.add(r)
                added += 1
        target[char] = sorted(existing, key=lambda x: (len(x), x))
    return added


def merge_words(target: Dict[str, str], source: Dict[str, str], prefer_target: bool = True) -> int:
    """Merge word-level meanings. Trả về số entries mới thêm.

    prefer_target=True: giữ nghĩa hiện có trong target (không ghi đè).
    prefer_target=False: ghi đè bằng nghĩa mới từ source.
    """
    added = 0
    for han, vi in source.items():
        if han not in target:
            target[han] = vi
            added += 1
        elif not prefer_target:
            target[han] = vi
    return added


def load_existing_glossary(path: Path) -> Dict[str, str]:
    """Đọc glossary.json hiện tại (file thật trong project root)."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] Không đọc được {path}: {e}", file=sys.stderr)
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Hán Việt dictionaries from various sources")
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=Path(r"C:\Users\quock\AppData\Local\Temp\opencode\dict-sources"),
        help="Thư mục chứa các repo đã clone",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(r"F:\Clone\novel-translate-mobile"),
        help="Thư mục project (để ghi dictionaries/ và merge glossary.json)",
    )
    parser.add_argument(
        "--no-merge-existing",
        action="store_true",
        help="Không merge với glossary.json hiện có (ghi đè từ đầu)",
    )
    parser.add_argument(
        "--no-crawl",
        action="store_true",
        help="Không crawl rongmotamhon.net (mặc định vẫn crawl nếu thiếu)",
    )
    args = parser.parse_args()

    src = args.sources_dir
    project = args.project_dir
    dict_dir = project / "dictionaries"
    dict_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"  Build Hán Việt dictionaries")
    print(f"  Sources: {src}")
    print(f"  Output:  {dict_dir}")
    print("=" * 72)

    chars_final: Dict[str, List[str]] = {}
    words_final: Dict[str, str] = {}

    # ------------------------------------------------------------------------
    # 1. CVDICT.u8 (122K entries) - largest source
    # ------------------------------------------------------------------------
    print("\n[1/5] CVDICT (ph0ngp/CVDICT - CC BY-SA 4.0)...")
    cvdict_path = src / "CVDICT" / "CVDICT.u8"
    cvdict_words = load_cvdict_text(cvdict_path)
    added = merge_words(words_final, cvdict_words, prefer_target=False)
    print(f"  → {len(cvdict_words):,} entries loaded, {added:,} mới thêm vào words")

    # ------------------------------------------------------------------------
    # 2. hanviet-pinyin-wordlist (~11K chars)
    # ------------------------------------------------------------------------
    print("\n[2/5] hanviet-pinyin-wordlist (ph0ngp - MIT)...")
    csv_path = src / "hanviet-pinyin-wordlist" / "hanviet.csv"
    csv_chars = load_hanviet_csv(csv_path)
    added = merge_chars(chars_final, csv_chars)
    print(f"  → {len(csv_chars):,} chars loaded, {added:,} readings mới thêm")

    # ------------------------------------------------------------------------
    # 3. chinese-hanviet-cognates (TSV + phienam.txt + vietphrases.txt)
    # ------------------------------------------------------------------------
    print("\n[3/5] chinese-hanviet-cognates (ryanphung)...")
    cog_dir = src / "chinese-hanviet-cognates"

    cog_tsv = cog_dir / "outputs" / "chinese-hanviet-cognates.tsv"
    cog_words = load_cognates_tsv(cog_tsv)
    added = merge_words(words_final, cog_words, prefer_target=False)
    print(f"  → cognates.tsv: {len(cog_words):,} entries, {added:,} mới thêm")

    phienam = cog_dir / "inputs" / "phienam.txt"
    phienam_chars = load_phienam(phienam)
    added = merge_chars(chars_final, phienam_chars)
    print(f"  → phienam.txt:  {len(phienam_chars):,} chars, {added:,} readings mới thêm")

    vietphrases = cog_dir / "inputs" / "vietphrases.txt"
    vp_words = load_vietphrases(vietphrases)
    added = merge_words(words_final, vp_words, prefer_target=False)
    print(f"  → vietphrases.txt: {len(vp_words):,} phrases, {added:,} mới thêm")

    # ------------------------------------------------------------------------
    # 4. chugiai-zh-en-vi (JSON format)
    # ------------------------------------------------------------------------
    print("\n[4/5] chugiai-zh-en-vi (thaoshibe - CC BY-SA 4.0)...")
    chugiai_dir = src / "chugiai-zh-en-vi"
    cvdict_json_path = chugiai_dir / "cvdict_full.json"
    cvdict_json_words = load_cvdict_json(cvdict_json_path)
    added = merge_words(words_final, cvdict_json_words, prefer_target=False)
    print(f"  → cvdict_full.json: {len(cvdict_json_words):,} entries, {added:,} mới thêm")

    # ------------------------------------------------------------------------
    # 5. hanzi-sino-vietnamese (659 HSK chars)
    # ------------------------------------------------------------------------
    print("\n[5/5] hanzi-sino-vietnamese (binhbuithithanh - CC BY 4.0)...")
    hanzi_dir = src / "hanzi-sino-vietnamese"
    hanzi_chars = load_hanzi_sino(hanzi_dir / "data" / "characters.json")
    added = merge_chars(chars_final, hanzi_chars)
    print(f"  → characters.json: {len(hanzi_chars):,} HSK chars, {added:,} readings mới thêm")

    # ------------------------------------------------------------------------
    # 6. (Optional) Crawl rongmotamhon.net
    # ------------------------------------------------------------------------
    if not args.no_crawl:
        crawl_path = dict_dir / "rongmotamhon_raw.json"
        if crawl_path.exists():
            print("\n[6/7] rongmotamhon.net (skip - đã có cache)")
            try:
                with crawl_path.open("r", encoding="utf-8") as f:
                    rmh_words = json.load(f)
                added = merge_words(words_final, rmh_words, prefer_target=False)
                print(f"  → cache: {len(rmh_words):,} entries, {added:,} mới thêm")
            except (json.JSONDecodeError, OSError):
                print(f"  → cache lỗi, bỏ qua")
        else:
            print("\n[6/7] rongmotamhon.net: chưa crawl, bỏ qua (chạy crawl_rongmotamhon.py riêng)")
    else:
        print("\n[6/7] rongmotamhon.net: skipped (--no-crawl)")

    # ------------------------------------------------------------------------
    # 7. Seed terms (xianxia/urban/wuxia - manual curated)
    # ------------------------------------------------------------------------
    print("\n[7/7] Seed terms (xianxia/urban/wuxia - dictionaries/xianxia_terms.py)...")
    seed_path = dict_dir / "xianxia_terms.py"
    if seed_path.exists():
        # Import dynamically
        import importlib.util
        spec = importlib.util.spec_from_file_location("xianxia_terms", seed_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            seed_terms = getattr(mod, "ALL_SEED_TERMS", {})
            added = merge_words(words_final, seed_terms, prefer_target=False)
            print(f"  → {len(seed_terms):,} seed terms, {added:,} mới thêm")
        else:
            print(f"  [SKIP] Không load được {seed_path}")
    else:
        print(f"  [SKIP] Không tìm thấy {seed_path}")

    # ------------------------------------------------------------------------
    # Merge với glossary.json hiện có (giữ entries của user)
    # ------------------------------------------------------------------------
    existing_glossary_path = project / "glossary.json"
    if not args.no_merge_existing and existing_glossary_path.exists():
        print(f"\n[Merge] {existing_glossary_path}...")
        existing = load_existing_glossary(existing_glossary_path)
        before = len(words_final)
        # Giữ existing entries ưu tiên (không ghi đè)
        for k, v in existing.items():
            words_final.setdefault(k, v)
        print(f"  → {len(existing):,} entries từ glossary.json, tổng {len(words_final):,} (Δ +{len(words_final) - before:,})")

    # ------------------------------------------------------------------------
    # Ghi output
    # ------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("  Ghi output...")
    print("=" * 72)

    chars_out = dict_dir / "hanviet_chars.json"
    words_out = dict_dir / "hanviet_words.json"

    with chars_out.open("w", encoding="utf-8") as f:
        json.dump(chars_final, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {chars_out.relative_to(project)}: {len(chars_final):,} chars")

    with words_out.open("w", encoding="utf-8") as f:
        json.dump(words_final, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {words_out.relative_to(project)}: {len(words_final):,} words")

    # Backup và merge vào glossary.json (chính)
    if not args.no_merge_existing and existing_glossary_path.exists():
        backup_path = existing_glossary_path.with_suffix(
            f".json.bak.{__import__('datetime').datetime.now():%Y%m%d_%H%M%S}"
        )
        # Dùng PowerShell-style backup để khớp với convention trong AGENTS.md
        import shutil
        shutil.copy2(existing_glossary_path, backup_path)
        print(f"  [BAK] {backup_path.name}")

    with existing_glossary_path.open("w", encoding="utf-8") as f:
        json.dump(words_final, f, ensure_ascii=False, indent=2)
    print(f"  [OK] {existing_glossary_path.relative_to(project)}: {len(words_final):,} entries (merged)")

    # ------------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("  THỐNG KÊ TỔNG KẾT")
    print("=" * 72)
    print(f"  Chữ Hán có Hán Việt reading: {len(chars_final):,}")
    print(f"  Cụm từ có nghĩa Việt:        {len(words_final):,}")

    # Đếm entries dài (>=2 chars)
    long_entries = {k: v for k, v in words_final.items() if len(k) >= 2}
    print(f"      - trong đó cụm từ (≥2 chữ): {len(long_entries):,}")

    # Sample
    print("\n  Sample entries (random từ CVDICT):")
    import random
    sample_keys = random.sample(list(words_final.keys()), min(8, len(words_final)))
    for k in sample_keys:
        print(f"    {k:20s} = {words_final[k][:80]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())