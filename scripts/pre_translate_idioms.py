"""
pre_translate_idioms.py - Pre-translate thanh ngu Trung-Viet TRUOC khi goi DeepSeek API.

Ly do: DeepSeek rat manh cho dich van xuoi hien dai, nhuong khi gap THANH NGU
(成语/thành ngữ), CA DAO, TỤC NGỮ Trung Quoc thi hay dich sai hoac dich tho nguyen
âm Hán Việt (vd: 'cuu long cố thuat' thay vi 'nín thở').

Cach hoat dong:
1. Load idioms_verified.json (4,483 chengyu 4 char co marker (thành ngữ) verified)
   - Moi idiom co ca 2 variant: simp + trad (vi du '一刀两断' va '一刀兩斷')
2. Voi moi chuong: scan text, tim longest-match thành ngữ (greedy)
3. Tra trong mapping lay ban dich co dinh
4. Thay the truc tiep vao chapter text (string substitution voi zero-width space marker)
5. DeepSeek chi can dich phan con lai (van xuoi + dialogue)

Luu y: Pre-translate CHI xu ly chengyu 4 char co marker (thành ngữ) - rat an toan.
Khong xu ly cum tu thuong, danh tu ky thuat, etc.

Output vao chapter moi voi zero-width space (\u200B) bao quanh de DeepSeek nhan
dien "phan nay da dich san, khong sua". Sau khi DeepSeek tra ve, ta strip marker.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional


# File chứa danh sách chengyu đã verify
IDIOMS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dictionaries", "idioms_verified.json"
)

# Zero-width space marker de ngan DeepSeek "sua" phan da dich san
MARKER = "\u200B"


@lru_cache(maxsize=1)
def load_idioms(path: str = IDIOMS_PATH) -> dict:
    """Load mapping {idiom_simp/trad: ban_dich_VN} tu idioms_verified.json.

    Returns:
        {
            "idioms": set[str],           # Tat ca variants
            "translations": dict[str, str],  # idiom -> vi
            "lengths": list[int],         # do dai co the (sort desc)
        }
    """
    p = Path(path)
    if not p.exists():
        return {"idioms": set(), "translations": {}, "lengths": []}

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Combine simple formats (simp + trad) tu chengyu_4char_simple
    translations: dict[str, str] = {}
    translations.update(data.get("chengyu_4char_simple", {}))
    translations.update(data.get("long_idioms_simple", {}))

    lengths = sorted(set(len(k) for k in translations.keys()), reverse=True)

    return {
        "idioms": set(translations.keys()),
        "translations": translations,
        "lengths": lengths,
    }


def extract_idiom_spans(text: str, idiom_set: set[str], lengths: list[int]) -> list[tuple[int, int, str]]:
    """Quet text, tra ve list cac span (start, end, idiom) khong overlap.

    Thuat toan: Greedy longest-match
    - Duyet qua tung vi tri trong text
    - Tai moi vi tri, thu match longest idiom truoc, 4 char sau
    - Skip neu vi tri hien tai da nam trong span da chon
    """
    spans = []
    used = [False] * len(text)

    for start in range(len(text)):
        if used[start]:
            continue
        for length in lengths:
            end = start + length
            if end > len(text):
                continue
            if any(used[i] for i in range(start, end)):
                break
            candidate = text[start:end]
            if candidate in idiom_set:
                spans.append((start, end, candidate))
                for i in range(start, end):
                    used[i] = True
                break

    return sorted(spans, key=lambda x: x[0])


def pre_translate_text(text: str, idiom_data: dict, max_replace: int = 50) -> tuple[str, list[dict]]:
    """Pre-translate thanh ngu trong text.

    Args:
        text: Doan van goc (Chinese)
        idiom_data: Output cua load_idioms()
        max_replace: Gioi han so idiom thay the / 1 doan (tranh replace qua nhieu)

    Returns:
        (text_da_thay_the, list_replace_log)
    """
    if not idiom_data["idioms"]:
        return text, []

    spans = extract_idiom_spans(text, idiom_data["idioms"], idiom_data["lengths"])
    if not spans:
        return text, []

    if len(spans) > max_replace:
        spans = spans[:max_replace]

    # Thay the tu phai qua trai
    result = text
    log = []
    for start, end, zh in reversed(spans):
        vi = idiom_data["translations"][zh]
        # Wrap voi zero-width space de DeepSeek khong sua phan dich san
        result = result[:start] + f"{MARKER}{vi}{MARKER}" + result[end:]
        log.append({"zh": zh, "vi": vi, "pos": start})

    log.reverse()
    return result, log


def pre_translate_chapter(chapter: dict, idiom_data: dict, log_func=None) -> dict:
    """Pre-translate tat ca paragraphs trong 1 chuong.

    Returns:
        Chapter dict moi voi:
        - paragraphs: cac doan van da duoc pre-translate
        - title: giu nguyen
        - _pre_translate_log: list[dict] tong hop (optional)
    """
    new_chapter = {
        "title": chapter["title"],
        "paragraphs": [],
    }
    all_log = []

    for para in chapter.get("paragraphs", []):
        new_para, log = pre_translate_text(para, idiom_data)
        new_chapter["paragraphs"].append(new_para)
        all_log.extend(log)

    if log_func and all_log:
        log_func(f"  Pre-translate: {len(all_log)} thanh ngu")

    new_chapter["_pre_translate_log"] = all_log
    return new_chapter


def restore_pre_translated(text: str) -> str:
    """Loai bo zero-width space markers con sot lai (sau khi DeepSeek tra ve).

    DeepSeek co the dich them phan text nằm GIUA 2 markers (vd them tua de,
    noi dung giai thich). Cho nen ta KHONG xoa toan bo, ma chi xoa nhung
    markers con SOT lai (cặp mo-dong khong can thiet).
    """
    return text.replace(MARKER, "")


# Test
if __name__ == "__main__":
    import io, sys
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, OSError):
            pass

    print("Loading idioms...")
    data = load_idioms()
    print(f"Total idioms (simp+trad variants): {len(data['idioms']):,}")
    print(f"Lengths: {data['lengths']}")

    # Test voi cac cau co chengyu
    test_cases = [
        "他守株待兔地等了半天。",          # co 守株待兔 (giong nhau ca simp/trad)
        "一刀两断，从此江湖路远。",         # simp
        "自強不息，永远前进。",              # trad
        "天行健，君子以自强不息。",         # mixed
        "画蛇添足，适得其反。",              # simp
        "臥薪嘗膽，十年生聚。",              # trad
        "不管三七二十一，先斩后奏。",         # co 4-char trong glossary
        "天气预报说明天会下雨。",            # KHONG phai chengyu
        "守株待兔和一刀两断都是成语。",       # 2 chengyu
    ]

    print("\n=== Test pre-translate ===")
    for tc in test_cases:
        spans = extract_idiom_spans(tc, data["idioms"], data["lengths"])
        translated, log = pre_translate_text(tc, data)
        restored = restore_pre_translated(translated)
        print(f"\nInput:    {tc}")
        print(f"Spans:    {spans}")
        print(f"Output:   {translated}")
        print(f"Restored: {restored}")
