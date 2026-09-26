"""
prepare_novel.py - Buoc chuan bi TRUOC khi dich: quet toan bo truyen da cao, lap san
glossary ten rieng va bang cach dich thanh ngu bang model suy luan cao (high).

Vi sao: neu chi hoc ten trong luc dich, ten duoc chot o lan xuat hien dau tien voi rat it
ngu canh, va dich song song nhieu chuong co the dat 1 ten 2 kieu. Buoc nay nhin ca truyen
mot luot nen chot ten/thanh ngu mot lan cho ca bo.

1. Ten rieng (code, khong ton tien): dem cum chu Han 2-6 chu lap lai nhieu lan, giu cum
   dung doc lap (ben trai/phai da dang) va dinh chat (khong phai 2 tu ghep ngau nhien),
   bo tu thong dung (tu dien Han Viet) va thanh ngu -> vai tram ung vien kem 1 cau trich.
2. Ten rieng (model, high): loc ung vien that la ten nguoi/biet danh/dia danh/to chuc,
   cho cach dich co dinh. Ten da co trong glossary KHONG bao gio bi ghi de.
3. Thanh ngu (model, high): moi thanh ngu trong truyen chua co cach dich -> 1 cach dich
   theo IDIOM_PRIORITY_RULES, ghi vao tu dien thanh ngu cua truyen (source "chuan_bi").

Ghi nho da xet gi vao <file dich>_prepare.json: chay lai chi goi API cho ten/thanh ngu MOI
(vd truyen cao them chuong), khong co gi moi thi khong goi API.

translate_novel() tu goi buoc nay (tat bang --no-prepare). Chay tay de xem truoc:
  python prepare_novel.py --raw "Truyen_raw.txt" --output "Truyen_raw.txt.viet.txt"
  python prepare_novel.py ... --no-api     # chi in ung vien ten, khong goi API
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from build_idiom_dictionary import pretranslate, scan_novel
from deepseek_translate import (_CJK_RE, _CJK_RUN_RE, DEFAULT_MODEL, _chapter_text, _idiom_detector,
                                _novel_base, call_deepseek, glossary_path_for, idioms_path_for,
                                load_curated_idioms, load_dotenv, load_glossary, load_idiom_memory,
                                merge_new_terms, normalize_zh, save_glossary, save_idiom_memory)

PREPARE_EFFORT = "high"
NAME_BATCH = 150
MAX_NAME_CANDIDATES = 600   # ung vien khong co trong tu dien, lay theo so lan xuat hien
MAX_COMMON_CANDIDATES = 200  # tu co trong tu dien nhung hay gap - co the la biet danh (大兵 = "lính")
_HANVIET_WORDS = Path(__file__).resolve().parent / "dictionaries" / "hanviet_words.json"

# Chu dau/cuoi cum gan nhu khong bao gio la mot phan cua ten ("看着大兵", "大兵说").
_STOP_START = set("的了着过是在与我你他她它这那就也都不没说把被给对向从又还很要会能想去有个吗呢吧啊呀么让位辆些们")
_STOP_END = set("的了着过是在与我你他她它们这那就也都不说把被给对向从又还很要会能想去有个吗呢吧啊呀么让地得")
_SURNAMES = set("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程"
                "苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛"
                "郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰"
                "焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁"
                "蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂"
                "全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻苑迟邝栗上欧司")

NAME_PROMPT = """Bạn là biên tập viên dịch tiểu thuyết Trung -> Việt, đang lập bảng TÊN RIÊNG (glossary)
cho CẢ BỘ truyện trước khi dịch. Mọi chương sau sẽ bị ép dùng đúng nguyên văn bảng này.

Đầu vào: mỗi dòng "cụm chữ Hán | số lần xuất hiện | câu trích". Các cụm do máy lọc thống kê nên
phần lớn KHÔNG phải tên: từ thường, cụm ghép dở, tên dính động từ/trợ từ.

CHỈ GIỮ:
- Tên người, biệt danh, tên gọi tắt của nhân vật (kể cả khi chữ đó cũng là từ thường, miễn trong
  câu trích nó được dùng làm tên - VD 大兵 là tên gọi nhân vật thì giữ).
- Họ + chức danh dùng như tên gọi cố định (VD 石处长 -> "Trưởng phòng Thạch", 高政委 -> "Chính ủy Cao").
- Địa danh, cơ quan, tổ chức, công ty, sản phẩm có tên riêng.
BỎ: từ thông thường, chức danh không kèm họ, cách gọi thân mật đổi theo ngữ cảnh (老X, 小X, X哥,
X姐), cụm dính động từ/trợ từ/tên khác (看着大兵, 尹白鸽轻声, 八喜和九贵), cụm bị cắt dở, thành ngữ.
Không chắc là tên thì BỎ - chương dịch sau vẫn tự học tên còn thiếu.

CÁCH DỊCH:
- Tên người Trung Quốc: âm Hán Việt, viết hoa mỗi âm tiết (任九贵 -> "Nhậm Cửu Quý"); chữ đa âm
  chọn âm đúng cho tên. Tên gọi tắt phải khớp tên đầy đủ (九贵 -> "Cửu Quý").
- Tên nước ngoài: cách phiên âm/viết quen dùng ở Việt Nam.
- Địa danh, tổ chức: phần tên riêng theo Hán Việt viết hoa, phần chỉ loại dịch nghĩa
  (岚海市 -> "thành phố Lam Hải", 洛川派出所 -> "đồn công an Lạc Xuyên").
- Họ + chức danh: chức danh dịch theo cách gọi tự nhiên của người Việt, đứng trước họ
  (顾总 -> "Giám đốc Cố" hoặc "sếp Cố", KHÔNG viết "Tổng Cố"); cùng một chức danh (总, 厅, 局, 所...)
  phải dịch giống nhau cho mọi người và khớp với tên cơ quan tương ứng.
- Biệt danh có nghĩa (王秃子, 大兵) dịch sao cho người Việt hiểu đó là biệt danh
  (VD 王秃子 -> "Vương Trọc"), trừ khi "Tên đã chốt" đã có cách dịch.
- Phải khớp với "Tên đã chốt" (nếu có): không dịch lại các tên đó, tên mới cùng họ/cùng gốc phải
  viết cùng kiểu.

Trả lời DUY NHẤT bằng JSON: {"names": {"cụm chữ Hán": {"vi": "bản dịch", "loai": "nguoi|dia_danh|to_chuc|khac"}}}
chỉ gồm các cụm được GIỮ, khóa đúng nguyên văn cụm ở đầu vào."""


def state_path_for(output_file: str) -> str:
    return _novel_base(output_file) + "_prepare.json"


def load_state(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


@lru_cache(maxsize=1)
def _common_words() -> frozenset:
    """Tu thong dung = muc trong tu dien Han Viet ma nghia viet thuong ("lính", "cảnh sát").
    Muc nghia viet hoa ("Bát Hỉ", "Công An Phường") la ten rieng, khong tinh."""
    try:
        with open(_HANVIET_WORDS, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return frozenset()
    out = set()
    for zh, vi in data.items():
        first = next((ch for ch in str(vi) if ch.isalpha()), "")
        if first and first.islower():
            out.add(normalize_zh(zh))
    return frozenset(out)


def _entropy(counter: Counter) -> float:
    """Do da dang cua chu dung ben canh. Dau/cuoi doan ("^"/"$") tinh moi lan la 1 chu khac."""
    total = sum(counter.values())
    edge = counter.get("^", 0) + counter.get("$", 0)
    ent = -sum(n / total * math.log(n / total) for ch, n in counter.items() if ch not in "^$")
    return ent + (edge / total * math.log(total) if edge else 0.0)


def find_name_candidates(chapters: list[dict], max_len: int = 6, min_count: int | None = None,
                         limit: int = MAX_NAME_CANDIDATES,
                         common_limit: int = MAX_COMMON_CANDIDATES) -> list[dict]:
    """Ung vien ten rieng tu thong ke, khong goi API. Tra ve [{zh, count, example, common}]
    theo thu tu uu tien (xuat hien nhieu truoc). min_count mac dinh tang theo do dai truyen
    (5 lan voi truyen < 1 trieu chu) de truyen rat dai khong sinh qua nhieu ung vien."""
    texts = [_chapter_text(ch) for ch in chapters]
    runs = [run for text in texts for run in _CJK_RUN_RE.findall(text)]
    total = sum(map(len, runs)) or 1
    if min_count is None:
        min_count = max(5, total // 200_000)

    counts: Counter = Counter()
    for run in runs:
        counts.update(run)
    level = {ch for ch, n in counts.items() if n >= min_count}
    grams: set[str] = set()
    for n in range(2, max_len + 1):
        c: Counter = Counter()
        for run in runs:
            for i in range(len(run) - n + 1):
                g = run[i:i + n]
                if g[:-1] in level and g[1:] in level:
                    c[g] += 1
        level = {g for g, k in c.items() if k >= min_count}
        counts.update({g: c[g] for g in level})
        grams |= level

    idioms = set(_idiom_detector()) | set(load_curated_idioms())
    grams = {g for g in grams if g not in idioms and g[0] not in _STOP_START and g[-1] not in _STOP_END}
    left: dict[str, Counter] = defaultdict(Counter)
    right: dict[str, Counter] = defaultdict(Counter)
    for run in runs:
        size = len(run)
        for n in range(2, max_len + 1):
            for i in range(size - n + 1):
                g = run[i:i + n]
                if g in grams:
                    left[g][run[i - 1] if i else "^"] += 1
                    right[g][run[i + n] if i + n < size else "$"] += 1

    def cohesion(g: str) -> float:
        # Cum dinh chat: xuat hien cung nhau nhieu hon han ngau nhien (PMI dang ti so).
        return min(counts[g] * total / (counts[g[:i]] * counts[g[i:]]) for i in range(1, len(g)))

    keep = {g: counts[g] for g in grams
            if min(_entropy(left[g]), _entropy(right[g])) >= 1.0 and cohesion(g) >= 20}
    def parts(h: str):
        return {h[i:j] for i in range(len(h)) for j in range(i + 2, len(h) + 1) if j - i < len(h)}

    common = _common_words()
    drop = set()
    for h, n in keep.items():
        for g in parts(h) & keep.keys():
            # Cum ngan nam trong cum dai gan nhu moi lan (洛川 trong 洛川派出所) -> bo cum ngan.
            if n >= 0.8 * keep[g]:
                drop.add(g)
            # Cum dai = ten quen thuoc + 1 chu/tu thuong (纪震道, 纪震总队长, 大兵严肃) -> bo cum dai.
            # Tru ho + ten (王八喜 = 王 + 八喜): do la ten day du.
            else:
                rest = h.replace(g, "", 1)
                if len(rest) == 1 and h.startswith(rest) and rest in _SURNAMES:
                    continue
                if (len(rest) == 1 and keep[g] >= 2 * n) or (rest in common and keep[g] >= 5 * n):
                    drop.add(h)
    keep = {g: n for g, n in keep.items() if g not in drop}

    def rank(item):
        g, n = item
        bonus = 2 if g[0] in _SURNAMES and len(g) <= 3 else 1
        return -n * bonus

    rare = sorted(((g, n) for g, n in keep.items() if g not in common), key=rank)[:limit]
    usual = sorted(((g, n) for g, n in keep.items() if g in common), key=rank)[:common_limit]

    def example(g: str, second: bool = False) -> str:
        found = []
        for text in texts:
            pos = text.find(g)
            if pos >= 0:
                found.append(text[max(0, pos - 18):pos + len(g) + 18].replace("\n", " ").strip())
                if len(found) == (2 if second else 1):
                    break
        return " / ".join(found)

    return ([{"zh": g, "count": n, "example": example(g), "common": False} for g, n in rare]
            + [{"zh": g, "count": n, "example": example(g, True), "common": True} for g, n in usual])


def _is_name_rendering(vi: str) -> bool:
    # Cung tieu chi voi clean_new_terms: ten rieng co it nhat 2 tu viet hoa.
    return (bool(vi) and len(vi) <= 60 and not _CJK_RE.search(vi)
            and sum(w[:1].isupper() for w in vi.split()) >= 2)


def decide_names(candidates: list[dict], known: dict, api_key: str, model: str = DEFAULT_MODEL,
                 reasoning_effort: str = PREPARE_EFFORT, workers: int = 4, log=print,
                 should_stop=None) -> dict:
    """Goi model loc/dich ung vien theo lo. Lo dau (nhan vat chinh, xuat hien nhieu nhat) chay
    truoc de cac lo sau co "Ten da chot" ma viet cung kieu. Tra ve {zh: {"vi", "loai"}}."""
    batches = [candidates[i:i + NAME_BATCH] for i in range(0, len(candidates), NAME_BATCH)]
    decided: dict[str, dict] = {}

    def run(batch: list[dict], fixed: dict) -> dict:
        if should_stop and should_stop():
            return {}
        fixed_block = "\n".join(f"{zh} = {vi}" for zh, vi in list(fixed.items())[:400])
        user = ((f"Tên đã chốt:\n{fixed_block}\n\n" if fixed_block else "")
                + "Cụm | số lần | câu trích:\n"
                + "\n".join(f"{c['zh']} | {c['count']} | {c['example']}" for c in batch))
        usage: dict = {}
        data = call_deepseek(NAME_PROMPT, user, api_key, model, temperature=1.0, thinking=True,
                             max_tokens=65536, on_usage=usage.update, reasoning_effort=reasoning_effort)
        allowed = {c["zh"] for c in batch}
        good = {}
        for zh, info in ((data or {}).get("names") or {}).items():
            zh = normalize_zh(str(zh).strip())
            info = info if isinstance(info, dict) else {"vi": info}
            vi = str(info.get("vi", "")).strip()
            if zh in allowed and _is_name_rendering(vi):
                good[zh] = {"vi": vi, "loai": str(info.get("loai", "")).strip()}
        log(f"  Ten rieng: lo {len(batch)} ung vien -> giu {len(good)} "
            f"(token vao {usage.get('prompt_tokens', '?')}, ra {usage.get('completion_tokens', '?')})")
        return good

    if not batches:
        return decided
    decided.update(run(batches[0], dict(known)))
    fixed = {**known, **{zh: d["vi"] for zh, d in decided.items()}}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for good in pool.map(lambda b: run(b, fixed), batches[1:]):
            decided.update(good)
    return decided


def prepare_novel(chapters: list[dict], output_file: str, glossary_path: str | None, api_key: str,
                  model: str = DEFAULT_MODEL, reasoning_effort: str = PREPARE_EFFORT,
                  style_guide: str = "", workers: int = 4, log=print, should_stop=None,
                  use_api: bool = True) -> dict:
    """Chay buoc chuan bi cho 1 truyen. Ghi glossary + tu dien thanh ngu + file trang thai.
    Ten da co trong glossary khong gui lai model (chi dua vao "Ten da chot").
    Tra ve tom tat {"names_added", "idioms_added", "skipped"}."""
    glossary_path = glossary_path or glossary_path_for(output_file)
    state_path = state_path_for(output_file)
    state = load_state(state_path)
    summary = {"names_added": {}, "idioms_added": 0, "skipped": False}
    if state.get("chapters") == len(chapters) and state.get("done"):
        log(f"[Chuan bi] Da chuan bi cho {len(chapters)} chuong truoc do, bo qua.")
        summary["skipped"] = True
        return summary

    log(f"[Chuan bi] Quet {len(chapters)} chuong tim ten rieng va thanh ngu...")
    names_checked = set(state.get("names_checked", []))
    idioms_checked = set(state.get("idioms_checked", []))
    glossary = load_glossary(glossary_path)
    in_glossary = {normalize_zh(k) for k in glossary}
    candidates = [c for c in find_name_candidates(chapters)
                  if c["zh"] not in names_checked and c["zh"] not in in_glossary]

    idiom_path = idioms_path_for(output_file)
    memory = load_idiom_memory(idiom_path)
    counts, examples = scan_novel(chapters)
    curated = load_curated_idioms()
    for key, n in counts.items():
        entry = memory.setdefault(key, {"vi": "", "approved": False, "source": "truyen"})
        entry["freq"] = n
        entry.setdefault("example", examples.get(key, ""))
    idiom_todo = [k for k, _ in counts.most_common()
                  if k not in curated and k not in idioms_checked
                  and not memory[k].get("approved") and not memory[k].get("variants")
                  and memory[k].get("source") != "chuan_bi"]
    log(f"[Chuan bi] {len(candidates)} ung vien ten moi can xet, {len(idiom_todo)} thanh ngu can dich.")

    if not use_api:
        return {**summary, "candidates": candidates, "idiom_todo": idiom_todo}

    if candidates:
        decided = decide_names(candidates, glossary, api_key, model, reasoning_effort, workers, log, should_stop)
        if should_stop and should_stop():
            return summary
        summary["names_added"] = merge_new_terms(glossary, {zh: d["vi"] for zh, d in decided.items()})
        save_glossary(glossary_path, glossary)
        state.setdefault("names", {}).update(decided)
        names_checked |= {c["zh"] for c in candidates}
        log(f"[Chuan bi] Them {len(summary['names_added'])} ten vao {glossary_path} "
            f"(tong {len(glossary)}).")

    if idiom_todo:
        got = pretranslate(idiom_todo, examples, api_key, model, log=log, reasoning_effort=reasoning_effort,
                           style_guide=style_guide, workers=workers, should_stop=should_stop)
        if should_stop and should_stop():
            return summary
        for key, vi in got.items():
            memory[key].update(vi=vi, source="chuan_bi")
        idioms_checked |= set(idiom_todo)
        summary["idioms_added"] = len(got)
        log(f"[Chuan bi] Dich san {len(got)}/{len(idiom_todo)} thanh ngu vao {idiom_path}.")
    save_idiom_memory(idiom_path, memory)

    state.update(chapters=len(chapters), done=True, names_checked=sorted(names_checked),
                 idioms_checked=sorted(idioms_checked), updated=datetime.now().isoformat(timespec="seconds"))
    save_state(state_path, state)
    return summary


def main() -> None:
    from crawler import parse_chapters

    ap = argparse.ArgumentParser(description="Buoc chuan bi: lap glossary ten rieng + thanh ngu truoc khi dich")
    ap.add_argument("--raw", required=True, help="File truyen da cao (tieng Trung)")
    ap.add_argument("--output", required=True, help="File dich (glossary/tu dien dat canh file nay)")
    ap.add_argument("--glossary", default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-api", action="store_true", help="Chi in ung vien, khong goi API")
    ap.add_argument("--env-file", default=".env")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    chapters = parse_chapters(args.raw)
    api_key = ""
    if not args.no_api:
        load_dotenv(args.env_file)
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            sys.exit("Thieu DEEPSEEK_API_KEY")
    result = prepare_novel(chapters, args.output, args.glossary, api_key, model=args.model,
                           use_api=not args.no_api)
    if args.no_api:
        for c in result.get("candidates", []):
            print(f"{c['zh']}\t{c['count']}\t{'tu dien' if c['common'] else ''}\t{c['example']}")


if __name__ == "__main__":
    main()
