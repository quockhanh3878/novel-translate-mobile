"""Offline cost estimates for translating a novel with DeepSeek."""

import argparse
import threading
import time
from pathlib import Path

from crawler import is_novel_title_entry, parse_chapters
from deepseek_translate import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT


# Source: actual DeepSeek-flash measurements supplied for 2026-10-07 and 2026-09-26.
# The range is USD per source character, using the sum of chapter paragraphs.
RATE_LOW = 3.9e-6
RATE_AVERAGE = 4.4e-6
RATE_HIGH = 5.7e-6

# Source: DeepSeek-flash low/off-peak pricing supplied for this task.
PRICE_PER_MILLION = {
    "prompt_cache_hit_tokens": 0.003,
    "prompt_cache_miss_tokens": 0.15,
    "completion_tokens": 0.6,
}

# These are estimates, not measured prices for each reasoning setting.
REASONING_FACTORS = {
    "low": 0.95,
    "medium": 1.0,
    "high": 1.0,
    "max": 1.2,
}


def _reasoning_factor(reasoning_effort, no_thinking):
    if no_thinking:
        return 0.25, "no_thinking"
    effort = str(reasoning_effort or DEFAULT_REASONING_EFFORT).lower()
    return REASONING_FACTORS.get(effort, 1.0), effort


def _warnings(model, effort, no_thinking):
    warnings = []
    if model != DEFAULT_MODEL:
        warnings.append("Chưa có bảng giá cho model này; tạm tính theo giá deepseek-flash.")
    if no_thinking or effort in ("low", "high", "max"):
        warnings.append("Hệ số mức suy luận là giả định, chưa có số đo riêng.")
    return warnings


def _chapter_data(path):
    chapters = parse_chapters(path)
    title_offset = 1 if is_novel_title_entry(chapters, 0) else 0
    real_chapters = chapters[title_offset:]
    chapter_chars = [sum(len(paragraph) for paragraph in chapter.get("paragraphs", []))
                     for chapter in real_chapters]
    return real_chapters, chapter_chars


def _costs(chars, factor, peak):
    peak_factor = 2.0 if peak else 1.0
    return {
        "low": chars * RATE_LOW * factor * peak_factor,
        "average": chars * RATE_AVERAGE * factor * peak_factor,
        "high": chars * RATE_HIGH * factor * peak_factor,
    }


def _result(total_chars, chapters, translated_chapters=0, model=DEFAULT_MODEL,
            reasoning_effort=DEFAULT_REASONING_EFFORT, no_thinking=False, peak=False,
            warnings=None, translated_path=None, remaining_chars_override=None,
            crawled_chapters=None):
    factor, effort = _reasoning_factor(reasoning_effort, no_thinking)
    translated_chapters = max(0, min(int(translated_chapters), int(chapters)))
    remaining_chars = total_chars
    if remaining_chars_override is not None:
        remaining_chars = max(0, int(remaining_chars_override))
    elif chapters:
        average_chars = total_chars / chapters
        remaining_chars = max(0, int(round(average_chars * (chapters - translated_chapters))))
    total_cost = _costs(total_chars, factor, peak)
    remaining_cost = _costs(remaining_chars, factor, peak)
    all_warnings = list(warnings or [])
    all_warnings.extend(_warnings(model, effort, no_thinking))
    if crawled_chapters is None:
        crawled_chapters = chapters
    return {
        "available": True,
        "model": model,
        "pricing_model": DEFAULT_MODEL,
        "reasoning_effort": effort,
        "no_thinking": bool(no_thinking),
        "reasoning_factor": factor,
        "peak": bool(peak),
        "is_peak_hour": bool(peak),
        "peak_multiplier": 2.0 if peak else 1.0,
        "chapters": int(chapters),
        "crawled_chapters": max(0, min(int(crawled_chapters), int(chapters))),
        "translated_chapters": translated_chapters,
        "remaining_chapters": int(chapters) - translated_chapters,
        "total_chars": int(total_chars),
        "remaining_chars": remaining_chars,
        "cost_total": total_cost,
        "cost_remaining": remaining_cost,
        "full_cost": total_cost,
        "total_cost": total_cost,
        "cost_left": remaining_cost,
        "remaining_cost": remaining_cost,
        "warnings": all_warnings,
        "translated_path": translated_path,
    }


def estimate_chars(total_chars, chapters, model=DEFAULT_MODEL,
                   reasoning_effort=DEFAULT_REASONING_EFFORT, no_thinking=False,
                   peak=False):
    """Estimate a novel from a known source character count and chapter count."""
    try:
        total_chars = int(total_chars)
        chapters = int(chapters)
    except (TypeError, ValueError):
        return {"available": False, "reason": "Số ký tự và số chương không hợp lệ.", "warnings": []}
    if total_chars < 0 or chapters < 0:
        return {"available": False, "reason": "Số ký tự và số chương phải không âm.", "warnings": []}
    return _result(total_chars, chapters, model=model, reasoning_effort=reasoning_effort,
                   no_thinking=no_thinking, peak=peak)


def estimate_file(raw_path, translated_path=None, model=DEFAULT_MODEL,
                  reasoning_effort=DEFAULT_REASONING_EFFORT, no_thinking=False,
                  peak=False):
    """Estimate a raw novel file using the shared crawler chapter parser."""
    raw_path = Path(raw_path)
    if not raw_path.is_file():
        return {"available": False, "reason": "Không tìm thấy file thô.", "warnings": []}
    if raw_path.suffix.lower() != ".txt":
        return {"available": False, "reason": "Chỉ chấp nhận file .txt.", "warnings": []}
    try:
        if raw_path.stat().st_size == 0:
            return {"available": False, "reason": "File thô rỗng.", "warnings": []}
        _, chapter_chars = _chapter_data(str(raw_path))
    except (OSError, UnicodeError, ValueError) as exc:
        return {"available": False, "reason": "Không đọc được file thô: %s" % exc, "warnings": []}
    if not chapter_chars:
        return {"available": False, "reason": "File thô chưa có chương nào có nội dung.", "warnings": []}

    translated_chapters = 0
    warnings = []
    if translated_path:
        translated_path = Path(translated_path)
        if translated_path.is_file() and translated_path.suffix.lower() == ".txt":
            try:
                translated_chapters = len(_chapter_data(str(translated_path))[0])
            except (OSError, UnicodeError, ValueError) as exc:
                warnings.append("Không đọc được file dịch: %s" % exc)
        else:
            warnings.append("Không thấy file dịch; tính phần còn lại từ đầu.")

    result = _result(sum(chapter_chars), len(chapter_chars), translated_chapters,
                     model=model, reasoning_effort=reasoning_effort,
                     no_thinking=no_thinking, peak=peak, warnings=warnings,
                     translated_path=str(translated_path) if translated_path else None,
                     remaining_chars_override=sum(chapter_chars[translated_chapters:]),
                     crawled_chapters=len(chapter_chars))
    result["raw_path"] = str(raw_path)
    return result


# Catalog estimate (site with an adapter, novel not crawled yet): the catalog gives the chapter
# count; the average length comes from a few sample chapters. Cached so that changing the model
# or reasoning level on the page does not hit the site again.
SAMPLE_CHAPTERS = 2
SAMPLE_DELAY_SECONDS = 2.0
ERROR_CACHE_SECONDS = 60
_CATALOG_CACHE = {}
_CATALOG_LOCK = threading.Lock()


def _sample_catalog(url, adapter, sleep=time.sleep, now=time.time):
    key = adapter.catalog_url(url) or url
    with _CATALOG_LOCK:
        cached = _CATALOG_CACHE.get(key)
        if cached and (cached["ok"] or now() - cached["at"] < ERROR_CACHE_SECONDS):
            return cached
        chapters = adapter.list_chapters(url, log=lambda *_: None)
        entry = {"ok": False, "at": now(), "reason": "Không đọc được mục lục của trang."}
        if chapters:
            count = len(chapters)
            step = max(1, count // SAMPLE_CHAPTERS)
            picks = sorted({min(i * step, count - 1) for i in range(SAMPLE_CHAPTERS)})
            lengths = []
            for n, index in enumerate(picks):
                if n:
                    sleep(SAMPLE_DELAY_SECONDS)
                sample = adapter.crawl_chapter(chapters[index]["url"], log=lambda *_: None)
                if sample:
                    lengths.append(sum(len(p) for p in sample["paragraphs"]))
            if lengths:
                entry = {"ok": True, "at": now(), "chapters": count,
                         "avg_chars": sum(lengths) / len(lengths), "sampled": len(lengths)}
            else:
                entry["reason"] = "Không đọc được chương mẫu của trang."
        _CATALOG_CACHE[key] = entry
        return entry


def estimate_catalog(url, adapter, model=DEFAULT_MODEL, reasoning_effort=DEFAULT_REASONING_EFFORT,
                     no_thinking=False, peak=False, sleep=time.sleep, now=time.time):
    """Estimate a novel that is not crawled yet, from its catalog and a few sample chapters."""
    info = _sample_catalog(url, adapter, sleep=sleep, now=now)
    if not info["ok"]:
        return {"available": False, "reason": info["reason"], "warnings": []}
    result = estimate_chars(round(info["chapters"] * info["avg_chars"]), info["chapters"], model=model,
                            reasoning_effort=reasoning_effort, no_thinking=no_thinking, peak=peak)
    result["crawled_chapters"] = 0
    result["warnings"].insert(0, "Chưa cào truyện: ước tính từ mục lục và %d chương mẫu của trang." % info["sampled"])
    return result


def usd_from_usage(usage_dict, model=DEFAULT_MODEL, peak=False):
    """Calculate actual USD from one DeepSeek usage object."""
    usage_dict = usage_dict or {}
    total = 0.0
    for key, price in PRICE_PER_MILLION.items():
        try:
            tokens = float(usage_dict.get(key) or 0)
        except (TypeError, ValueError):
            tokens = 0.0
        total += tokens / 1_000_000.0 * price
    return total * (2.0 if peak else 1.0)


def _print_result(result):
    if not result.get("available"):
        print("Khong the uoc tinh: %s" % result.get("reason", "ly do khong ro"))
        return 1
    total = result["cost_total"]
    remaining = result["cost_remaining"]
    print("Uoc tinh chi phi dich toan bo")
    print("So chuong: %d" % result["chapters"])
    print("Tong ky tu nguon: %d" % result["total_chars"])
    print("Da dich: %d chuong; con lai: %d ky tu" %
          (result["translated_chapters"], result["remaining_chars"]))
    print("Toan bo: $%.2f - $%.2f (trung binh $%.2f)" %
          (total["low"], total["high"], total["average"]))
    print("Con lai: $%.2f - $%.2f (trung binh $%.2f)" %
          (remaining["low"], remaining["high"], remaining["average"]))
    print("Gia cao diem: %s" % ("co" if result["peak"] else "khong"))
    if result["warnings"]:
        print("Canh bao:")
        for warning in result["warnings"]:
            print("- %s" % warning)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Uoc tinh chi phi dich toan bo truyen")
    parser.add_argument("file", help="File tho .txt")
    parser.add_argument("--translated", help="File ban dich da co")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", default=DEFAULT_REASONING_EFFORT,
                        choices=("low", "medium", "high", "max"))
    parser.add_argument("--no-thinking", action="store_true")
    parser.add_argument("--peak", action="store_true",
                        help="Gia dinh goi API trong gio cao diem")
    args = parser.parse_args()
    result = estimate_file(args.file, args.translated, args.model,
                           args.reasoning_effort, args.no_thinking, args.peak)
    raise SystemExit(_print_result(result))


if __name__ == "__main__":
    main()
