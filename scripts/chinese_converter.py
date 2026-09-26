"""
chinese_converter.py - Chuyen doi Simplified <-> Traditional dung opencc-python-reimplemented.

Dung cho viec PRE-TRANSLATE: Khi chapter Trung Quoc su dung phien ban
simplified/traditional khac voi set chengyu verified (chua 1 phien ban),
can chuyen doi de match.

Vi du:
- '一刀两断' (simp) -> '一刀兩斷' (trad) de match trong set chengyu verified
- '自强不息' (simp) -> '自強不息' (trad) de match
"""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_converter_s2t():
    """Lazy load Simp -> Trad converter."""
    try:
        from opencc import OpenCC
        return OpenCC('s2t')  # Simplified to Traditional
    except Exception:
        return None


@lru_cache(maxsize=1)
def _get_converter_t2s():
    """Lazy load Trad -> Simp converter."""
    try:
        from opencc import OpenCC
        return OpenCC('t2s')  # Traditional to Simplified
    except Exception:
        return None


def simp_to_trad(text: str) -> str:
    """Chuyen Simplified -> Traditional. Tra ve text goc neu OpenCC loi."""
    if not text:
        return text
    try:
        conv = _get_converter_s2t()
        if conv is None:
            return text
        return conv.convert(text)
    except Exception:
        return text


def trad_to_simp(text: str) -> str:
    """Chuyen Traditional -> Simplified."""
    if not text:
        return text
    try:
        conv = _get_converter_t2s()
        if conv is None:
            return text
        return conv.convert(text)
    except Exception:
        return text


def ensure_variants(text: str) -> tuple[str, str]:
    """Tra ve (simp, trad) cua text. Neu OpenCC OK thi return 2 phien ban."""
    if not text:
        return (text, text)
    simp = text
    trad = simp_to_trad(text)
    if trad == simp:
        # Co the la pure Han pure simp, thu nguoc
        simp2 = trad_to_simp(text)
        if simp2 != text:
            simp = simp2
            trad = text
    return (simp, trad)


if __name__ == "__main__":
    import io, sys
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    test_cases = [
        "一刀两断",      # simp
        "一刀兩斷",      # trad
        "自强不息",      # simp
        "自強不息",      # trad
        "守株待兔",      # giong nhau
        "画蛇添足",      # simp
        "畫蛇添足",      # trad
        "卧薪尝胆",      # simp
        "臥薪嘗膽",      # trad
        "天气预报",      # simp tu thuong
    ]

    print("=== Test simp -> trad ===")
    for tc in test_cases:
        result = simp_to_trad(tc)
        print(f"  {tc:12s} -> {result:12s}  {'OK' if result != tc or 'simp' in tc else 'IDENTICAL'}")

    print("\n=== Test trad -> simp ===")
    for tc in test_cases:
        result = trad_to_simp(tc)
        print(f"  {tc:12s} -> {result:12s}")

    print("\n=== Test ensure_variants ===")
    for tc in test_cases:
        simp, trad = ensure_variants(tc)
        print(f"  {tc:12s} -> simp={simp:12s} trad={trad}")
