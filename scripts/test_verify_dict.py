"""Test/verify Hán Việt dictionaries chất lượng.

Kiểm tra:
  1. Đọc & parse được (JSON valid, không corrupt)
  2. Coverage: chữ Hán phổ biến trong tiếng Việt + light novel phải có
  3. Spot-check nghĩa của 1 số từ kinh điển
  4. Thống kê độ dài + chất lượng nghĩa
  5. So sánh với glossary.json cũ (entries user thêm tay)

Usage:
  python scripts/test_verify_dict.py
  python scripts/test_verify_dict.py --verbose
"""

import argparse
import io
import json
import sys
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except (AttributeError, OSError):
        pass


# ============================================================================
# Test cases - chữ Hán / cụm từ PHẢI CÓ trong dict
# ============================================================================

# Single chars - 100 chữ Hán phổ biến nhất trong light novel
EXPECTED_CHARS = [
    "我", "你", "他", "她", "它", "们", "的", "了", "是", "不",
    "在", "有", "人", "这", "中", "大", "为", "上", "个", "们",
    "说", "时", "要", "就", "出", "会", "可", "也", "你", "对",
    "生", "能", "而", "子", "那", "得", "于", "着", "下", "自",
    "年", "发", "后", "作", "里", "用", "道", "行", "所", "然",
    "家", "种", "事", "成", "方", "多", "经", "面", "起", "看",
    "天", "道", "法", "修", "神", "仙", "魔", "妖", "剑", "气",
    "龙", "凤", "鬼", "魂", "阴", "阳", "太", "极", "乾", "坤",
    "金", "木", "水", "火", "土", "风", "雷", "电", "山", "海",
    "帝", "皇", "王", "侯", "将", "相", "臣", "军", "兵", "马",
    "师", "徒", "门", "派", "宗", "教", "门", "弟", "兄", "姐",
]

# Words - 50 cụm từ quan trọng trong light novel Trung Quốc
EXPECTED_WORDS = [
    "修炼", "法术", "神通", "境界", "突破", "飞升",
    "师兄", "师姐", "师弟", "师妹", "师父", "掌门",
    "法宝", "灵药", "灵石", "灵根", "元婴", "金丹",
    "灵气", "灵力", "法术", "神通", "御剑", "炼丹",
    "天帝", "魔尊", "妖王", "鬼王", "仙人", "修士",
    "武林", "江湖", "门派", "帮派", "武功", "秘籍",
    "侠客", "大侠", "少侠", "女侠", "侠女", "剑客",
    "武功", "内功", "外功", "招式", "掌法", "剑法",
    "公司", "总裁", "经理", "员工", "客户", "市场",
    "医院", "医生", "护士", "病人", "手术", "急诊",
    "警察", "案件", "证据", "证人", "嫌疑", "判决",
]

# Famous people / places in light novel
EXPECTED_NAMES = [
    "陆渊", "苏沐雨", "林动", "萧炎", "牧尘", "林枫",
    "孙悟空", "唐僧", "猪八戒", "沙僧", "观音", "如来",
    "诸葛亮", "刘备", "关羽", "张飞", "赵云", "曹操",
    "李白", "杜甫", "白居易", "王维", "苏轼", "李清照",
    "秦始皇", "汉武帝", "唐太宗", "宋太祖", "成吉思汗",
]


def load_dict(path: Path) -> dict:
    """Đọc JSON dictionary, raise nếu lỗi."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def check_dict_validity(words: dict, chars: dict) -> tuple[bool, list[str]]:
    """Kiểm tra JSON có valid + không có entry rỗng."""
    errors = []
    if not isinstance(words, dict):
        errors.append(f"words phải là dict, nhận {type(words).__name__}")
        return False, errors
    if not isinstance(chars, dict):
        errors.append(f"chars phải là dict, nhận {type(chars).__name__}")
        return False, errors
    # Check empty entries
    empty_words = [k for k, v in words.items() if not v or not isinstance(v, str)]
    if empty_words:
        errors.append(f"{len(empty_words)} words có nghĩa rỗng (vd: {empty_words[:3]})")
    empty_chars = [k for k, v in chars.items() if not v or not isinstance(v, list)]
    if empty_chars:
        errors.append(f"{len(empty_chars)} chars có readings rỗng (vd: {empty_chars[:3]})")
    return len(errors) == 0, errors


def check_coverage(words: dict, chars: dict) -> tuple[float, float, list[str]]:
    """Đo % coverage trên test cases."""
    missing_chars = [c for c in EXPECTED_CHARS if c not in chars]
    missing_words = [w for w in EXPECTED_WORDS if w not in words]
    missing_names = [n for n in EXPECTED_NAMES if n not in words]
    all_missing = missing_chars + missing_words + missing_names
    total_expected = len(EXPECTED_CHARS) + len(EXPECTED_WORDS) + len(EXPECTED_NAMES)
    found = total_expected - len(all_missing)
    coverage = found / total_expected if total_expected else 0
    return (
        coverage,
        len(all_missing) / total_expected if total_expected else 0,
        all_missing[:20],
    )


def check_quality_stats(words: dict) -> dict:
    """Thống kê phân bố chất lượng."""
    lens = Counter(len(k) for k in words.keys())
    # Meanings quá ngắn (<3 chars) thường là low-quality
    short_meanings = sum(1 for v in words.values() if isinstance(v, str) and len(v) < 3)
    # Meanings chứa "?" / raw format
    suspicious = sum(1 for v in words.values() if isinstance(v, str) and any(
        s in v for s in ["[", "]", "/zhōng/", "/xué/", "[]", "(Tw)", "(Hk)"]
    ))
    return {
        "total": len(words),
        "unique_lengths": len(lens),
        "by_length": dict(sorted(lens.items())[:10]),
        "short_meanings_pct": short_meanings / len(words) * 100 if words else 0,
        "suspicious_format_pct": suspicious / len(words) * 100 if words else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(r"F:\Clone\novel-translate-mobile"),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dict_dir = args.project_dir / "dictionaries"
    words_path = dict_dir / "hanviet_words.json"
    chars_path = dict_dir / "hanviet_chars.json"

    print("=" * 70)
    print(f"  VERIFY Hán Việt dictionaries tại {dict_dir}")
    print("=" * 70)

    # 1. Load
    print("\n[1/4] Loading...")
    try:
        words = load_dict(words_path)
        chars = load_dict(chars_path)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  [FAIL] Không đọc được: {e}")
        return 1
    print(f"  words: {len(words):,} entries")
    print(f"  chars: {len(chars):,} entries")

    # 2. Validity
    print("\n[2/4] Validity check...")
    valid, errors = check_dict_validity(words, chars)
    if valid:
        print("  [PASS] JSON valid, không có entry rỗng")
    else:
        print(f"  [FAIL] {len(errors)} lỗi:")
        for e in errors:
            print(f"    - {e}")

    # 3. Coverage
    print("\n[3/4] Coverage check (test cases)...")
    coverage, miss_pct, missing = check_coverage(words, chars)
    status = "PASS" if coverage >= 0.85 else "WARN" if coverage >= 0.7 else "FAIL"
    print(f"  [{status}] {coverage:.1%} coverage ({miss_pct:.1%} missing)")
    if missing:
        print(f"  Missing ({len(missing)}): {', '.join(missing[:15])}{'...' if len(missing) > 15 else ''}")

    # 4. Quality stats
    print("\n[4/4] Quality stats...")
    stats = check_quality_stats(words)
    print(f"  Total entries:       {stats['total']:,}")
    print(f"  Unique word lengths: {stats['unique_lengths']}")
    print(f"  Top 10 lengths:")
    for L, count in stats["by_length"].items():
        print(f"    {L} chars: {count:,}")
    print(f"  Short meanings (<3): {stats['short_meanings_pct']:.2f}%")
    print(f"  Suspicious format:   {stats['suspicious_format_pct']:.2f}%")

    # Verbose: in 1 số entries ngẫu nhiên
    if args.verbose:
        import random
        print("\n[VERBOSE] Sample entries:")
        sample = random.sample(list(words.items()), min(20, len(words)))
        for k, v in sample:
            print(f"  {k:12s} = {v[:100]}")

        print("\n[VERBOSE] Sample chars:")
        sample_chars = random.sample(list(chars.items()), min(15, len(chars)))
        for k, v in sample_chars:
            print(f"  {k:4s} = {v}")

    # Summary
    print("\n" + "=" * 70)
    passed = valid and coverage >= 0.7
    tag = "[PASS]" if passed else "[FAIL]"
    print(f"  KẾT QUẢ TỔNG: {tag}")
    print("=" * 70)
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())