"""
build_chengyu_set.py - Trich rieng set chengyu (4 char thanh ngu) chat luong cao
de dung trong pre_translate_idioms.py.

Tieu chi loc (uu tien chat luong > so luong):
1. Pure Han characters (4 chu Han lien tiep)
2. Co trong glossary.json
3. Co 1 trong cac markers nhan diet thanh ngu:
   - "(thành ngữ)", "(tục ngữ)", "(ca dao)", "(câu đối)", "(ngạn ngữ)"
4. KHONG chua tu khoa ky thuat (kinh te, y hoc, dia ly...) trong ban dich VN
5. Lay tu vietphrases.txt (human-verified) voi bo loc ky thuat

Sau khi loc, sinh ca 2 variant (simp + trad) cua moi idiom de pre_translate match
du ca 2 phien ban Trung Quoc.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = PROJECT_ROOT / "glossary.json"
VIETPHRASES_PATH = Path(r"C:\Users\quock\AppData\Local\Temp\opencode\dict-sources\chinese-hanviet-cognates\inputs\vietphrases.txt")
OUTPUT_PATH = PROJECT_ROOT / "dictionaries" / "idioms_verified.json"


def is_pure_han_4char(s: str) -> bool:
    """Check xem co phai 4 chu Han lien tiep khong."""
    return len(s) == 4 and all('\u4e00' <= c <= '\u9fff' for c in s)


def get_both_variants(text: str) -> tuple[str, str]:
    """Tra ve (simp, trad) cua text. Neu ko phan biet -> return goc."""
    from chinese_converter import simp_to_trad, trad_to_simp
    if not text:
        return (text, text)
    trad = simp_to_trad(text)
    if trad != text:
        return (text, trad)
    simp = trad_to_simp(text)
    if simp != text:
        return (simp, text)
    return (text, text)


def build_idioms_dict() -> dict[str, dict]:
    """Tra ve mapping chuan {idiom_canonical: {"vi": ban_dich, "simp": ..., "trad": ...}}.

    idiom_canonical: luon luon la phien ban TRADITIONAL (de thong nhat, tiet kiem
    entry khi simp va trad deu match). Mapping chi giu 1 dong trong output JSON.

    Criteria (uu tien chat luong):
    1. 4 chu Han lien tiep
    2. Co trong glossary.json
    3. Co 1 trong cac marker (thành ngữ, tục ngữ, ca dao, ...)
    4. HOAC co trong vietphrases.txt (human-verified) - tin cay tuong duong
    5. Khong phai cum ky thuat (kinh te, y hoc...) khi co vietphrases filter
    """
    with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
        glossary = json.load(f)

    # Load vietphrases set (cac cum da duoc human verify)
    vietphrases_set: set[str] = set()
    if VIETPHRASES_PATH.exists():
        with open(VIETPHRASES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^([^\s=]+)=', line)
                if m and is_pure_han_4char(m.group(1)):
                    vietphrases_set.add(m.group(1))

    print(f"4-char trong vietphrases.txt: {len(vietphrases_set):,}")

    final_canonical: dict[str, dict] = {}  # canonical_trad -> {vi, simp, trad}
    count_marker = 0
    count_vp = 0
    count_skipped = 0

    for k, v in glossary.items():
        if not is_pure_han_4char(k):
            continue
        v_lower = v.lower()
        has_marker = any(m in v_lower for m in ["(thành ngữ)", "(tục ngữ)", "(ca dao)", "(câu đối)",
                                                 "(ngạn ngữ)", "(cổ ngữ)"])

        # Quyet dinh co giu khong
        keep = False
        if has_marker:
            keep = True
            count_marker += 1
        elif k in vietphrases_set:
            # Co trong vietphrases nhung KHONG co marker (vd '自强不息', '自相矛盾')
            # Chi skip neu ban dich rat ngan (< 3 ky tu - co the sai)
            if len(v.strip()) < 3:
                count_skipped += 1
                continue
            # Trust vietphrases: da human verify, giu het
            keep = True
            count_vp += 1

        if not keep:
            continue

        # Lay ca 2 variant
        simp, trad = get_both_variants(k)
        canonical = trad if trad != simp else k
        if canonical not in final_canonical:
            final_canonical[canonical] = {"vi": v, "simp": simp, "trad": trad}

    print(f"4-char co marker (thành ngữ): {count_marker:,}")
    print(f"Them tu vietphrases.txt (verified): {count_vp:,}")
    print(f"Skipped (technical): {count_skipped:,}")
    print(f"Final 4-char chengyu: {len(final_canonical):,}")

    return final_canonical


def build_long_idioms(min_length: int = 8, max_length: int = 12) -> dict[str, dict]:
    """Lay long idioms (8-12 char) tu vietphrases. Dài hơn = câu văn, không phải idiom."""
    with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
        glossary = json.load(f)

    final: dict[str, dict] = {}
    if not VIETPHRASES_PATH.exists():
        return final

    count = 0
    with open(VIETPHRASES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^([^\s=]+)=', line)
            if m:
                phrase = m.group(1)
                n = len(phrase)
                if min_length <= n <= max_length and all('\u4e00' <= c <= '\u9fff' for c in phrase):
                    if phrase in glossary:
                        v = glossary[phrase]
                        v_lower = v.lower()
                        # Phai co marker idiom (chat che)
                        is_idiom = any(mk in v_lower for mk in
                                       ["(thành ngữ)", "(tục ngữ)", "(câu đối)",
                                        "(ngạn ngữ)", "(cổ ngữ)"])
                        if is_idiom and not re.search(r'[0-9a-zA-Z]', v):
                            simp, trad = get_both_variants(phrase)
                            canonical = trad if trad != simp else phrase
                            if canonical not in final:
                                final[canonical] = {"vi": v, "simp": simp, "trad": trad}
                                count += 1
    print(f"Long idioms ({min_length}-{max_length} char): {len(final):,}")
    return final


def to_simple_format(canonical_dict: dict[str, dict]) -> dict[str, str]:
    """Convert sang format {simp_form: vi} de pre_translate match truc tiep.

    Trong qua trinh pre-translate, ta quet text theo simp_form (pho bien hon
    trong truyen Trung Quoc hien dai). Neu gap simp_form -> thay bang 'vi'.
    """
    result: dict[str, str] = {}
    for canonical, info in canonical_dict.items():
        vi = info["vi"]
        # Map ca simp + trad (neu khac nhau) -> vi
        simp = info.get("simp", canonical)
        trad = info.get("trad", canonical)
        result[simp] = vi
        if trad != simp:
            result[trad] = vi
    return result


def main():
    import io
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    print("=== Build chengyu verified set (with simp/trad variants) ===\n")

    chengyu = build_idioms_dict()
    long_idioms = build_long_idioms()

    # Chuyen sang format {simp: vi} de pre_translate match
    chengyu_simple = to_simple_format(chengyu)
    long_simple = to_simple_format(long_idioms)

    output = {
        "chengyu_4char_simple": chengyu_simple,
        "long_idioms_simple": long_simple,
        # Giu ban goc co metadata de debug
        "_chengyu_4char": chengyu,
        "_long_idioms": long_idioms,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_simple = len(chengyu_simple) + len(long_simple)
    total_canonical = len(chengyu) + len(long_idioms)
    print(f"\nSaved to {OUTPUT_PATH}")
    print(f"  4-char chengyu canonical: {len(chengyu):,}")
    print(f"  4-char chengyu simp+trad: {len(chengyu_simple):,}")
    print(f"  long idioms canonical: {len(long_idioms):,}")
    print(f"  long idioms simp+trad: {len(long_simple):,}")
    print(f"  TOTAL simple forms: {total_simple:,} (vs {total_canonical:,} canonical)")


if __name__ == "__main__":
    main()
