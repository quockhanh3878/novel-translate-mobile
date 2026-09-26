"""
build_idiom_dictionary.py - Tao tu dien thanh ngu rieng cho 1 truyen TRUOC khi dich.

Buoc chuan bi (prepare_novel.py) goi scan_novel + pretranslate cua file nay moi khi dich,
nen thuong khong can chay tay. Chay tay de dich truoc rieng thanh ngu, hoac ap ket qua duyet.

1. Quet toan bo truyen da cao: thanh ngu nao xuat hien, o bao nhieu chuong, kem 1 cau vi du.
2. (Tuy chon) Goi DeepSeek 1-3 lan de dich truoc cac thanh ngu hay gap (mac dinh xuat hien
   tu 3 chuong tro len) sang thanh ngu/cach noi Viet tuong duong, co ngu canh cau vi du.
3. Ghi vao <file dich>_idioms.json - dung file ma deepseek_translate.py doc/ghi khi dich,
   de anh Ber duyet/sua. Muc da duyet (approved) khong bao gio bi ghi de.

Chay:
  python build_idiom_dictionary.py --raw "Truyen_raw.txt" --output "Truyen_raw.txt.viet.txt"
  python build_idiom_dictionary.py ... --no-api        # chi quet, khong goi API
  python build_idiom_dictionary.py --output "Truyen_raw.txt.viet.txt" --apply-review decisions.json
      # ap ket qua trang duyet (anh Ber duyet/sua/bo) vao tu dien
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from crawler import parse_chapters
import json

from concurrent.futures import ThreadPoolExecutor

from deepseek_translate import (_CJK_RE, _CURATED_IDIOMS_PATH, _idiom_detector, call_deepseek,
                                DEFAULT_MODEL, IDIOM_PRIORITY_RULES,
                                idioms_path_for,
                                load_curated_idioms, load_dotenv, load_idiom_memory,
                                normalize_zh, save_idiom_memory)

PRETRANSLATE_PROMPT = """Bạn là biên tập viên dịch tiểu thuyết Trung -> Việt, đang lập bảng cách dịch
thành ngữ cho CẢ BỘ truyện trước khi dịch. Với MỖI thành ngữ (kèm một câu trích trong truyện làm
ngữ cảnh), cho MỘT cách dịch tiếng Việt đặt thẳng được vào câu văn, chọn theo thứ tự ưu tiên:
""" + IDIOM_PRIORITY_RULES + """Giọng văn, xưng hô hợp với văn phong truyện ghi ở cuối (truyện hiện đại thì không dùng
"ngươi", "ta"). Không giải thích, không ghi chú, không còn chữ Hán.
Trả lời DUY NHẤT bằng JSON: {"idioms": {"thanh_ngu": "cach_dich"}} với đúng các khóa đã cho."""


def scan_novel(chapters: list[dict]) -> tuple[Counter, dict]:
    """Dem so chuong chua moi thanh ngu (tu dien chung + danh sach tuyen tay) va lay 1 cau vi du."""
    detector = _idiom_detector()
    curated = load_curated_idioms()
    long_keys = [k for k in curated if len(k) != 4]
    counts: Counter = Counter()
    examples: dict[str, str] = {}
    for ch in chapters:
        seen = set()
        for para in ch.get("paragraphs", []):
            text = normalize_zh(para)
            hits = [text[i:i + 4] for i in range(len(text) - 3)
                    if text[i:i + 4] in detector or text[i:i + 4] in curated]
            hits += [k for k in long_keys if k in text]
            for key in hits:
                if key in seen:
                    continue
                seen.add(key)
                counts[key] += 1
                if key not in examples:
                    pos = text.find(key)
                    examples[key] = text[max(0, pos - 30):pos + len(key) + 30].strip()
    return counts, examples


def pretranslate(keys: list[str], examples: dict, api_key: str, model: str,
                 batch_size: int = 120, log=print, reasoning_effort: str | None = "high",
                 style_guide: str = "", workers: int = 4, should_stop=None) -> dict:
    """Dich truoc thanh ngu theo lo (moi lo 1 lan goi API, chay song song `workers` lo).
    Chi nhan cach dich hop le: dung khoa da gui, khong con chu Han, khong phai "nghia den"."""
    style = f"\n\nVăn phong truyện: {style_guide}" if style_guide else ""
    batches = [keys[i:i + batch_size] for i in range(0, len(keys), batch_size)]

    def run(batch: list[str]) -> dict:
        if should_stop and should_stop():
            return {}
        lines = "\n".join(f"{k} | {examples.get(k, '')}" for k in batch)
        usage: dict = {}
        data = call_deepseek(PRETRANSLATE_PROMPT + style, "Thành ngữ | câu trích:\n" + lines, api_key, model,
                             temperature=1.0, thinking=True, max_tokens=65536,
                             on_usage=usage.update, reasoning_effort=reasoning_effort)
        got = data.get("idioms") if isinstance(data, dict) else None
        good = {}
        for k, v in (got or {}).items():
            key, vi = normalize_zh(str(k).strip()), str(v).strip()
            if key in batch and vi and len(vi) <= 60 and not _CJK_RE.search(vi) \
                    and not vi.lower().startswith("nghĩa đen"):
                good[key] = vi
        log(f"  Thanh ngu: lo {len(batch)} -> dung duoc {len(good)} "
            f"(token vao {usage.get('prompt_tokens', '?')}, ra {usage.get('completion_tokens', '?')})")
        return good

    out: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for good in pool.map(run, batches):
            out.update(good)
    return out


def apply_review(decisions: dict, memory: dict, curated_path: str) -> dict:
    """Ap quyet dinh tu trang duyet. decisions = {"items": {id: {zh, vi, status, src}}}.
    src "tuyen" -> sua/xoa trong danh sach tuyen tay (dung cho moi truyen);
    src "dich"  -> danh dau approved trong tu dien rieng cua truyen, hoac bo cach dich."""
    with open(curated_path, "r", encoding="utf-8") as f:
        curated = json.load(f)
    by_norm = {normalize_zh(k): k for k in curated}
    stats = Counter()
    for item in (decisions.get("items") or {}).values():
        key, vi, status = normalize_zh(item.get("zh", "")), (item.get("vi") or "").strip(), item.get("status")
        if not key or status not in ("approved", "rejected"):
            continue
        if item.get("src") == "tuyen" and key in by_norm:
            orig = by_norm[key]
            if status == "rejected":
                del curated[orig]
            elif vi and vi != curated[orig]:
                curated[orig] = vi
            stats[f"tuyen_{status}"] += 1
            continue
        entry = memory.setdefault(key, {"source": "dich_truoc"})
        if status == "approved" and vi and not _CJK_RE.search(vi):
            entry.update(vi=vi, approved=True)
        else:
            entry.update(vi="", approved=False, rejected=True)
        stats[f"dich_{status}"] += 1
    with open(curated_path, "w", encoding="utf-8") as f:
        json.dump(curated, f, ensure_ascii=False, indent=2)
    return dict(stats)


def main() -> None:
    ap = argparse.ArgumentParser(description="Tao tu dien thanh ngu rieng cho 1 truyen")
    ap.add_argument("--raw", help="File truyen da cao (tieng Trung)")
    ap.add_argument("--output", required=True, help="File dich (tu dien dat canh file nay)")
    ap.add_argument("--min-chapters", type=int, default=3,
                    help="Chi dich truoc thanh ngu xuat hien tu so chuong nay tro len")
    ap.add_argument("--limit", type=int, default=300, help="Toi da so thanh ngu dich truoc")
    ap.add_argument("--no-api", action="store_true", help="Chi quet truyen, khong goi API")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--apply-review", help="File JSON ket qua trang duyet")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    if args.apply_review:
        path = idioms_path_for(args.output)
        memory = load_idiom_memory(path)
        with open(args.apply_review, "r", encoding="utf-8") as f:
            decisions = json.load(f)
        print("Da ap:", apply_review(decisions, memory, str(_CURATED_IDIOMS_PATH)))
        save_idiom_memory(path, memory)
        return
    if not args.raw:
        ap.error("can --raw")

    chapters = parse_chapters(args.raw)
    counts, examples = scan_novel(chapters)
    path = idioms_path_for(args.output)
    memory = load_idiom_memory(path)
    for key, n in counts.items():
        entry = memory.setdefault(key, {"vi": "", "approved": False, "source": "truyen"})
        entry["freq"] = n
        entry.setdefault("example", examples.get(key, ""))
    print(f"Quet {len(chapters)} chuong: {len(counts)} thanh ngu, "
          f"{sum(1 for n in counts.values() if n >= args.min_chapters)} cai xuat hien tu "
          f"{args.min_chapters} chuong tro len.")

    if not args.no_api:
        load_dotenv(args.env_file)
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            sys.exit("Thieu DEEPSEEK_API_KEY")
        curated = load_curated_idioms()
        todo = [k for k, n in counts.most_common()
                if n >= args.min_chapters and k not in curated
                and not memory[k].get("vi") and not memory[k].get("approved")][:args.limit]
        print(f"Dich truoc {len(todo)} thanh ngu...")
        for key, vi in pretranslate(todo, examples, api_key, args.model).items():
            memory[key]["vi"] = vi
            memory[key]["source"] = "chuan_bi"

    save_idiom_memory(path, memory)
    print(f"Da ghi {len(memory)} muc vao {path}")


if __name__ == "__main__":
    main()
