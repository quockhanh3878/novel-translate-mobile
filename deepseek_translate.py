"""
deepseek_translate.py - Dich truyen da cao (format === Chuong === cua crawler.py)
sang tieng Viet bang DeepSeek API. Khong dung model MarianMT cuc bo.

Quy trinh de dam bao chat luong dong nhat xuyen suot truyen:
1. Doc DEEPSEEK_API_KEY tu file .env (hoac bien moi truong / --api-key).
2. Doc glossary.json (thu vien ten nhan vat/thuat ngu co dinh) lam ngu canh cho MOI
   lan goi API, dam bao ten rieng dich giong nhau tu dau den cuoi.
3. Truoc khi dich, goi API 1 lan de PHAN TICH VAN PHONG dua tren noi dung chuong dau
   (the loai, giong van, do trang trong/khau ngu...) -> tao 1 "style guide" ngan,
   dua vao system prompt cho toan bo cac chuong con lai de van phong dich nhat quan.
4. Voi moi chuong, model duoc yeu cau tra ve them "new_names": ten nhan vat/thuat ngu
   MOI xuat hien chua co trong glossary kem ban dich CO DINH cho no. Ten moi nay duoc
   gop ngay vao glossary dang dung trong RAM va ghi lai xuong glossary.json, de cac
   chuong sau (va cac lan chay sau) dung LAI CHINH XAC ten da chon, khong bi doi ten
   giua chung truyen.
5. Dau ra la JSON co cau truc {title, paragraphs[]} - map thang sang chuong EPUB,
   khong can dich lai/tach cau bang regex nhu khi dung model dich may cau ngan.

Vi buoc (4) can doc-sua glossary tuan tu de dam bao nhat quan, mac dinh chay TUAN TU
(--workers 1). Tang --workers giup dich nhanh hon nhung cac chuong dich song song se
khong thay ten moi cua nhau kip thoi -> co the dat ten khac nhau cho cung 1 nhan vat
o cac chuong gan nhau. Chi tang khi chap nhan danh doi do.

Khong import app.py/novel_gui.py vi 2 file do nap model MarianMT (ONNX) ngay khi
import - khong can thiet cho pipeline goi API nay.

Su dung:
    # .env: DEEPSEEK_API_KEY=sk-xxxx
    # PC (Windows): .venv\\Scripts\\python deepseek_translate.py --input truyen.txt --output truyen_viet.txt
    # Mobile (Termux) / Linux / macOS: .venv/bin/python deepseek_translate.py --input truyen.txt --output truyen_viet.txt
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import requests

from crawler import CHAPTER_SEP, count_chapters, is_novel_title_entry, parse_chapters
from text_postprocess import postprocess, postprocess_title

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# --- Connection pooling: reuse TCP/TLS connection giua cac API call ---
_SESSION = requests.Session()
_SESSION.headers.update({"Content-Type": "application/json"})

# Nguong max_tokens de tu dong bat streaming (chi translate_chapter vuot nguong nay)
_STREAM_THRESHOLD = 8192


# --- Write-ahead cache: luu ket qua API truoc khi ghi file chinh ---
# Tranh mat phi API khi crash/timeout giua luc postprocess hoac ghi file output.

def _cache_dir(output_file: str) -> str:
    """Thu muc cache nam cung cap voi file output."""
    return os.path.join(os.path.dirname(os.path.abspath(output_file)) or ".", ".translation_cache")


def _save_cache(output_file: str, chapter_idx: int, data: dict) -> None:
    d = _cache_dir(output_file)
    os.makedirs(d, exist_ok=True)
    cache_file = os.path.join(d, f"ch_{chapter_idx}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _load_cache(output_file: str, chapter_idx: int) -> dict | None:
    cache_file = os.path.join(_cache_dir(output_file), f"ch_{chapter_idx}.json")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _delete_cache(output_file: str, chapter_idx: int) -> None:
    cache_file = os.path.join(_cache_dir(output_file), f"ch_{chapter_idx}.json")
    try:
        os.remove(cache_file)
    except OSError:
        pass


def _clear_cache(output_file: str) -> None:
    """Xoa toan bo thu muc cache khi dich xong toan truyen."""
    d = _cache_dir(output_file)
    if os.path.isdir(d):
        import shutil
        try:
            shutil.rmtree(d)
        except OSError:
            pass
# Giu ten cu de tuong thich nguoc voi code/test da import truoc do.
count_translated_chapters = count_chapters


class InsufficientBalanceError(RuntimeError):
    """Tai khoan DeepSeek het so du, khong the tiep tuc goi API."""
    pass

# Gio cao diem DeepSeek (docs pricing): 01-04h va 06-10h UTC = 9h-12h va 14h-18h GIO BAC KINH
# (UTC+8), CHI thu 2 den thu 6 va TRU ngay le Trung Quoc ("excluding Chinese public holidays";
# ngay le va cuoi tuan la gia thap ca ngay). Ngay le lay tu thu vien `holidays` (CN, gom ca
# ngay nghi dieu chinh); thieu thu vien hoac nam chua co du lieu thi coi nhu ngay thuong
# (than trong: chi cho thua, khong goi nham gia gap doi).
# Trung Quoc khong dung DST nen offset co dinh, khong can zoneinfo/tzdata.
BEIJING_TZ = timezone(timedelta(hours=8))
PEAK_WINDOWS_BEIJING = [(9, 12), (14, 18)]  # [start, end) gio, dang 24h

DEFAULT_MODEL = "deepseek-flash"
# Muc suy luan mac dinh anh Ber chot (2026-09-26). DeepSeek chi co 3 muc thuc: low / high / max;
# "medium" duoc API quy ve "high" (docs thinking_mode). Da thu chuong 20-21: low dich thanh ngu
# kem hon, tat thinking sai nghia va sot chu Han nhieu.
DEFAULT_REASONING_EFFORT = "medium"
REASONING_EFFORTS = ("low", "medium", "high", "max")


@lru_cache(maxsize=8)
def _china_public_holidays(year: int) -> frozenset:
    """Cac ngay nghi le cua Trung Quoc trong nam (gom ngay nghi dieu chinh). Rong neu chua
    cai thu vien `holidays` hoac thu vien chua co du lieu nam do."""
    try:
        import holidays
        return frozenset(holidays.country_holidays("CN", years=year).keys())
    except Exception:
        return frozenset()


def is_peak_hour(now: datetime | None = None) -> bool:
    now = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    if now.weekday() >= 5:  # thu 7, chu nhat
        return False
    if now.date() in _china_public_holidays(now.year):
        return False
    return any(start <= now.hour < end for start, end in PEAK_WINDOWS_BEIJING)


def _peak_window_end(now: datetime) -> datetime:
    h = now.hour
    for start, end in PEAK_WINDOWS_BEIJING:
        if start <= h < end:
            return now.replace(hour=end, minute=0, second=0, microsecond=0)
    raise ValueError("now khong nam trong gio cao diem")


def wait_until_offpeak(log=print, should_stop=None, poll_seconds: int = 30) -> bool:
    """Neu dang trong gio cao diem, cho toi khi het gio cao diem moi tra ve. Kiem tra
    should_stop() moi vong poll de nguoi dung van dung duoc trong luc cho (co the cho
    toi vai gio neu roi dung dau gio cao diem). Tra ve True neu bi dung giua chung."""
    now = datetime.now(BEIJING_TZ)
    if not is_peak_hour(now):
        return False

    end = _peak_window_end(now)
    end_vn = end.astimezone(timezone(timedelta(hours=7)))
    log(f"Dang gio cao diem DeepSeek (gia gap doi) - tam dung goi API den {end.strftime('%H:%M')} "
        f"gio Bac Kinh ({end_vn.strftime('%H:%M')} gio VN).")

    while is_peak_hour():
        if should_stop and should_stop():
            log("Da dung trong luc cho het gio cao diem.")
            return True
        time.sleep(poll_seconds)

    log("Da het gio cao diem, tiep tuc.")
    return False

# Thu tu uu tien khi dich thanh ngu - rut tu 18 muc anh Ber duyet (2026-09). Dung chung cho
# prompt dich chuong va buoc chuan bi (prepare_novel.py) de hai noi dich cung mot tinh than.
IDIOM_PRIORITY_RULES = """   a) Thành ngữ, tục ngữ thuần Việt có cùng nghĩa bóng và hợp với câu, dù hình ảnh khác hẳn
      chữ Hán - kể cả khi chỉ gần nghĩa mà đọc thuận tai hơn (VD: 化整为零 -> "chia năm xẻ bảy",
      抛砖引玉 -> "thả tép bắt tôm", 焦头烂额 -> "sứt đầu mẻ trán", 五体投地 -> "phục sát đất").
   b) Cụm Hán Việt người Việt đã quen dùng (VD: "cam tâm tình nguyện", "cao cao tại thượng",
      "cận thủy lâu đài", "khắc thuyền tìm gươm", "cửu tử nhất sinh").
   c) Không có hai loại trên thì nói nghĩa bóng bằng khẩu ngữ gọn, tự nhiên (VD: 张口结舌 ->
      "cứng họng", 九牛一毛 -> "chẳng thấm vào đâu", 面面相觑 -> "nhìn nhau ngơ ngác").
   CẤM: dịch sát nghĩa đen từng chữ (SAI: "mặt nhìn mặt", "sấp mặt xuống đất", "há mồm lè lưỡi",
   "đèn mờ rượu đỏ"); để âm Hán Việt khó hiểu; mượn thành ngữ Việt nghe giống mà khác nghĩa
   (以牙还牙 là "ăn miếng trả miếng" chứ KHÔNG phải "gậy ông đập lưng ông" - câu đó là tự hại
   mình; 焦头烂额 là khốn đốn chứ KHÔNG phải "đầu tắt mặt tối" - câu đó là làm lụng vất vả).
"""

TRANSLATE_SYSTEM_PROMPT = """Ban la dich gia tieu thuyet mang chuyen nghiep, dich Trung -> Viet.
{style_guide_block}
Yeu cau bat buoc:
1. Dich tu nhien, dung van phong da xac dinh o tren, loi thoai song dong, khong dich
   tung chu mot cach may moc.
2. THÀNH NGỮ, TỤC NGỮ, ĐIỂN CỐ - chọn theo thứ tự ưu tiên:
""" + IDIOM_PRIORITY_RULES + """   Cuối prompt có danh sách thành ngữ của chương: nhóm "đã có cách dịch" thì dùng lại đúng
   cách dịch đó cho thống nhất cả truyện; nhóm "mới" chỉ là nghĩa tham khảo, KHÔNG chép nguyên.
   Liệt kê MỌI thành ngữ, tục ngữ, ngạn ngữ, 歇后语 đã dịch trong chương vào trường "idioms"
   (kể cả những cái đã có trong danh sách, không được để trống nếu chương có thành ngữ):
   khóa là nguyên văn chữ Hán trong chương, giá trị là ĐÚNG cụm tiếng Việt đã viết trong bản dịch.
   Thành ngữ KHÔNG đưa vào "new_terms".
3. TÊN RIÊNG trong glossary (tên nhân vật, biệt danh, địa danh, tổ chức): viết ĐÚNG NGUYÊN VĂN
   bản dịch trong glossary ở MỌI lần xuất hiện, giữ nguyên cách viết hoa. Không dịch nghĩa tên,
   không đổi sang cách viết khác, không thêm/bớt chữ. Glossary ở cuối prompt là bắt buộc.
4. Dung CHINH XAC ban thuat ngu (glossary) duoc cung cap o cuoi prompt cho ten nhan vat/dia danh/
   thuat ngu rieng, ap dung xuyen suot de dam bao tinh nhat quan giua cac chuong.
5. Neu gap ten nhan vat/dia danh, va {term_categories} CHUA co trong glossary, hay CHON MOT
   CACH DICH CO DINH duy nhat cho no va liet ke vao truong "new_terms" de dung lai
   cho cac chuong sau - khong duoc dich cung mot ten theo nhieu cach khac nhau.
   Tên người Trung Quốc dịch theo âm Hán Việt, viết hoa mỗi âm tiết (VD: 任九贵 -> "Nhậm Cửu Quý").
   Khóa của "new_terms" phải là chữ Hán xuất hiện nguyên văn trong chương. Không đưa thành ngữ
   hay từ thông thường vào "new_terms".
6. Giu nguyen so luong doan van dung bang so luong trong "paragraphs" dau vao,
   KHONG gop, KHONG tach, KHONG bo sot doan nao.
7. Khong them loi binh, khong them chu thich, khong dich thua noi dung khong co.
8. Dau ra phai la VAN BAN THUAN (plain text) cho tung doan, KHONG dung markdown,
   KHONG dung the HTML - vi ban dich se duoc dong goi thang vao EPUB.
9. Tra loi DUY NHAT bang JSON hop le theo dung schema:
   {{"title": "tieu de da dich", "paragraphs": ["doan 1 da dich", ...],
     "new_terms": {{"tu_trung_moi": "tu_viet_co_dinh"}},
     "idioms": {{"thanh_ngu_goc": "cum_tieng_Viet_da_dung_trong_ban_dich"}}}}

Vi du thanh ngu Trung -> thanh ngu/cach noi Viet tuong duong (THAM KHAO, ap dung tinh than nay):
  对牛弹琴 = đàn gảy tai trâu
  井底之蛙 = ếch ngồi đáy giếng
  班门弄斧 = múa rìu qua mắt thợ
  亡羊补牢 = mất bò mới lo làm chuồng
  盲人摸象 = thầy bói xem voi
  虎头蛇尾 = đầu voi đuôi chuột
  过河拆桥 = qua cầu rút ván
  狗急跳墙 = chó cùng rứt giậu
  趁火打劫 = thừa nước đục thả câu
  草木皆兵 = trông gà hóa cuốc
  杯水车薪 = muối bỏ bể
  笑里藏刀 = miệng nam mô, bụng một bồ dao găm
  守口如瓶 = kín miệng như bưng
  临时抱佛脚 = nước đến chân mới nhảy
  一箭双雕 = một mũi tên trúng hai đích
  入乡随俗 = nhập gia tùy tục
  塞翁失马 = tái ông mất ngựa
  画蛇添足 = vẽ rắn thêm chân

Vi du dich tho (giu y va nhip tho):
  床前明月光，疑是地上霜。举头望明月，低头思故乡。
  = Đầu giường ánh trăng rọi, ngỡ mặt đất phủ sương. Ngẩng đầu nhìn trăng sáng, cúi đầu nhớ cố hương.

Viec dich TIEU DE CHUONG:
- Neu tieu de goc co chua so chuong (vi du: "第1章", "第01章", "第十一回"...), bat buoc phai giu lai va dich dong nhat sang tieng Viet theo dinh dang "Chương X: [Ten chuong]" (vi du: "Chương 1: Đại biến người sống").
- Tieu de chuong ngan gon (2-8 tu), mang tinh thanh ngu/ngu co, truc dac.
- KHONG dich dai nhu cau van, KHONG them chu thich, KHONG viet hoa cau.
- Uu tien cach dich goi am, ngan gon, de nho. VD: "一念永恒" -> "Nhất niệm vĩnh hằng".
- Giu nguyen phong cach cua tieu de goc (neu goc ngan thi dich cung ngan).

{glossary_block}
"""

STYLE_SYSTEM_PROMPT = """Ban la bien tap vien tieu thuyet mang giau kinh nghiem.
Ban se doc nhieu doan trich tu NHIEU CHUONG khac nhau cua mot bo truyen tieng Trung
(lay tu dau, giua va cuoi truyen) va xac dinh phong cach dich tieng Viet phu hop nhat,
de ap dung NHAT QUAN cho toan bo truyen: the loai (vd tien hiep, do thi, ngon tinh,
trinh tham...), giong van (nghiem tuc/hai huoc/gai goc...), muc do trang trong hay
khau ngu, cach xung ho giua cac nhan vat.

Quan trong: phai tong hop tu nhieu mau o nhieu vung khac nhau trong truyen, khong chi
danh gia tren 1 chuong duy nhat. Neu phong cach thay doi giua cac vung, hay uu tien
phong cach CHUNG (xuat hien nhieu nhat) va ghi ro su thay doi neu co.
Tra loi DUY NHAT bang JSON: {
  "style_guide": "mo ta ngan gon 3-6 cau, bao gom the loai, giong van, muc do trang trong/khau ngu, cach xung ho, va phan tich tu nhieu vung truyen",
  "term_categories": "Liet ke cac loai thuat ngu dac trung cua the loai nay (vi du Tien hiep thi la: cong phap, tong mon, canh gioi, phap bao. Do thi thi la: chuc vu, cong ty, thuong hieu. V.v.) cung voi thanh ngu, tuc ngu."
}
"""


def sample_for_style(chapters: list[dict], num_chapters: int = 5, paragraphs_per_chapter: int = 30) -> list[dict]:
    """Chon ngau nhien cac chuong tu 3 vung (dau/giua/cuoi) de phan tich van phong.

    Tra ve list[dict] voi moi dict la {"title": ..., "paragraphs": [...]}.
    """
    valid = [c for c in chapters if c.get("paragraphs")]
    if not valid:
        return []
    n = len(valid)
    if n <= num_chapters:
        selected = valid
    else:
        # Chia 3 zone: dau (20%), giua (60%), cuoi (20%)
        zone_size = max(1, n // 5)
        first_zone = valid[:zone_size]
        mid_start = max(zone_size, n // 2 - zone_size)
        mid_end = min(n - zone_size, n // 2 + zone_size)
        mid_zone = valid[mid_start:mid_end]
        last_zone = valid[max(mid_end, n - zone_size):]

        # Lay 1-2 chuong ngau nhien tu moi zone
        per_zone = max(1, num_chapters // 3)
        sampled = []
        for zone in [first_zone, mid_zone, last_zone]:
            k = min(per_zone, len(zone))
            sampled.extend(random.sample(zone, k))
        # Neu con thieu, lay them tu toan bo
        remaining = [c for c in valid if c not in sampled]
        deficit = num_chapters - len(sampled)
        if deficit > 0 and remaining:
            sampled.extend(random.sample(remaining, min(deficit, len(remaining))))
        selected = sampled[:num_chapters]

    # Lay ngau nhien paragraphs tu moi chuong
    result = []
    for ch in selected:
        paras = ch["paragraphs"]
        k = min(paragraphs_per_chapter, len(paras))
        sampled_paras = random.sample(paras, k) if k < len(paras) else paras
        result.append({"title": ch.get("title", ""), "paragraphs": sampled_paras})
    return result


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_glossary(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_glossary(path: str, glossary: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2)


# --- Glossary Meta (tracking last_seen chapter + frequency) ---

def _meta_path(glossary_path: str) -> str:
    return glossary_path.rsplit(".", 1)[0] + "_meta.json"


def load_glossary_meta(glossary_path: str) -> dict:
    p = Path(_meta_path(glossary_path))
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_glossary_meta(glossary_path: str, meta: dict) -> None:
    with open(_meta_path(glossary_path), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def cleanup_glossary_meta(meta: dict, current_chapter: int,
                          max_idle_chapters: int = 100) -> tuple[dict, list]:
    """Loai bo metadata cua thuat ngu it dung (count=1) va lau khong xuat hien.
    CHI xoa meta, KHONG xoa khoi glossary: ten nhan vat xuat hien 1 lan roi quay lai
    sau 100+ chuong van phai giu dung ban dich cu, neu xoa model se dat ten moi.
    Tra ve (meta_moi, keys_da_xoa)."""
    keys_to_delete = []
    for zh, m in meta.items():
        if m.get("count", 1) == 1 and (current_chapter - m.get("last_seen", current_chapter)) > max_idle_chapters:
            keys_to_delete.append(zh)
    for k in keys_to_delete:
        del meta[k]
    return meta, keys_to_delete


def update_glossary_meta(meta: dict, new_names: dict, chapter_idx: int) -> dict:
    """Cap nhat metadata cho cac entry moi/da co."""
    for zh, vi in new_names.items():
        if zh in meta:
            meta[zh]["last_seen"] = chapter_idx
            meta[zh]["count"] = meta[zh].get("count", 0) + 1
        else:
            meta[zh] = {"last_seen": chapter_idx, "count": 1}
    return meta



# --- Chon thuat ngu + thanh ngu theo tung chuong ---
# Chi gui cho model nhung muc glossary THUC SU xuat hien trong chuong dang dich: vua it
# token, vua khong bo sot ten nhan vat cu (glossary lon bao nhieu cung duoc). So khop
# sau khi quy ve gian the (opencc) vi truyen cao ve co the la phon the ma glossary la
# gian the hoac nguoc lai.

_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_CJK_RUN_RE = re.compile(_CJK_RE.pattern + "+")
_IDIOMS_PATH = Path(__file__).resolve().parent / "dictionaries" / "idioms_verified.json"
_CURATED_IDIOMS_PATH = Path(__file__).resolve().parent / "dictionaries" / "idioms_curated.json"
MAX_GLOSSARY_PER_CHAPTER = 300
MAX_IDIOM_HINTS = 60


@lru_cache(maxsize=1)
def _t2s_converter():
    try:
        from opencc import OpenCC
        return OpenCC("t2s")
    except Exception:
        return None


@lru_cache(maxsize=None)
def normalize_zh(text: str) -> str:
    conv = _t2s_converter()
    return conv.convert(text) if conv else text


def _chapter_text(chapter: dict) -> str:
    return normalize_zh(chapter.get("title", "") + "\n" + "\n".join(chapter.get("paragraphs", [])))


def select_glossary_for_chapter(glossary: dict, chapter: dict,
                                max_entries: int = MAX_GLOSSARY_PER_CHAPTER) -> dict:
    """Tra ve cac muc glossary co mat trong chuong, giu thu tu chen trong glossary.
    Vuot max_entries thi uu tien cum dai (ten day du truoc ho/biet danh ngan)."""
    text = _chapter_text(chapter)
    hits = [zh for zh in glossary if zh and normalize_zh(zh) in text]
    if len(hits) > max_entries:
        keep = set(sorted(hits, key=len, reverse=True)[:max_entries])
        hits = [zh for zh in hits if zh in keep]
    return {zh: glossary[zh] for zh in hits}


# --- Tu dien thanh ngu ---
# Tu dien chung (idioms_verified.json, dich may tu tu dien Trung-Anh) CHI dung de NHAN DIEN
# thanh ngu; nghia cua no hay sat chu ("nghĩa đen: một cốc nước dập lửa...") nen khong dung
# lam cach dich. Cach dich lay tu 3 nguon, uu tien tu tren xuong:
#   1. Tu dien rieng cua truyen, muc anh Ber da duyet (approved).
#   2. dictionaries/idioms_curated.json - thanh ngu anh Ber tu tuyen, dung cho moi truyen.
#   3. Tu dien rieng cua truyen, cach dich model da dung o chuong truoc (lon dan khi dich).
# Thanh ngu chi la GOI Y (khong bat buoc nhu ten rieng) vi co ngu canh can dien dat khac.

def _clean_dict_meaning(vi: str) -> str:
    meaning = vi.replace("(thành ngữ)", "").strip(" ;,")
    low = meaning.lower()
    if (not meaning or low.startswith(("nghĩa đen", "xem ", "biến thể"))
            or _CJK_RE.search(meaning) or "[" in meaning):
        return ""
    return meaning


@lru_cache(maxsize=1)
def _idiom_detector() -> dict:
    """{thanh_ngu (gian the): nghia tham khao, hoac "" neu nghia chi la dich sat chu}."""
    try:
        with open(_IDIOMS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f).get("chengyu_4char_simple", {})
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for zh, vi in data.items():
        if "thành ngữ" not in vi:
            continue
        key = normalize_zh(zh)
        meaning = _clean_dict_meaning(vi)
        if key not in out or (meaning and not out[key]):
            out[key] = meaning
    return out


@lru_cache(maxsize=1)
def load_curated_idioms() -> dict:
    """{thanh_ngu (gian the): cach dich} tu dictionaries/idioms_curated.json."""
    try:
        with open(_CURATED_IDIOMS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return {normalize_zh(zh): vi for zh, vi in data.items() if zh and vi}


def _novel_base(output_file: str) -> str:
    return output_file.rsplit(".", 1)[0] if "." in os.path.basename(output_file) else output_file


def idioms_path_for(output_file: str) -> str:
    """Tu dien thanh ngu rieng cua truyen, dat canh file dich (cung kieu file _style.txt)."""
    return _novel_base(output_file) + "_idioms.json"


def glossary_path_for(output_file: str) -> str:
    """Glossary (ten rieng) rieng cua truyen, dat canh file dich. Moi truyen bat dau rong va
    tu hoc ten tu chuong dau: glossary chung dung cho moi truyen de ep nham ten truyen nay
    sang truyen khac (VD 大兵 la ten "Đại Binh" o truyen nay nhung la "lính" o truyen khac)."""
    return _novel_base(output_file) + "_glossary.json"


def load_idiom_memory(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_idiom_memory(path: str, memory: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def known_idiom_rendering(key: str, memory: dict | None) -> str:
    """Cach dich da co cho thanh ngu `key` (gian the), "" neu chua co. Chi tinh muc anh Ber
    da duyet, danh sach tuyen tay, hoac cach dich model DA DUNG THAT trong ban dich (co
    "variants"). Ban dich truoc (buoc chuan bi, chi 1 cau trich lam ngu canh) chua duyet thi
    chi la goi y: ep dung lai da thay dat sai cho (不以为然 "không tán thành" vao cau "cuoi xoa")."""
    entry = (memory or {}).get(key) or {}
    if entry.get("approved") and entry.get("vi"):
        return entry["vi"]
    curated = load_curated_idioms()
    if key in curated:
        return curated[key]
    return entry.get("vi", "") if entry.get("variants") else ""


def find_idioms_in_chapter(chapter: dict, skip: dict | None = None, memory: dict | None = None,
                           max_items: int = MAX_IDIOM_HINTS) -> tuple[dict, dict]:
    """Tim thanh ngu trong chuong (bo qua cum da co trong glossary `skip`).
    Tra ve (da_co, moi), khoa la dang gian the, theo thu tu xuat hien trong chuong:
      da_co {thanh_ngu: cach_dich} - da duyet/da tuyen/da dung o chuong truoc -> dung lai.
      moi   {thanh_ngu: nghia_tham_khao hoac ""} - lan dau gap.
    Ngoai thanh ngu 4 chu cua tu dien chung, con bat duoc cau dai (tuc ngu, 歇后语) mien la
    da co trong tu dien rieng cua truyen hoac danh sach tuyen tay."""
    text = _chapter_text(chapter)
    skipped = {normalize_zh(k) for k in (skip or {})}
    detector = _idiom_detector()
    first_pos: dict[str, int] = {}
    for key in list(memory or {}) + list(load_curated_idioms()):
        pos = text.find(key)
        if pos >= 0 and key not in skipped:
            first_pos.setdefault(key, pos)
    for i in range(len(text) - 3):
        key = text[i:i + 4]
        if key in detector and key not in skipped:
            first_pos.setdefault(key, i)
    known: dict[str, str] = {}
    fresh: dict[str, str] = {}
    for key in sorted(first_pos, key=first_pos.get)[:max_items]:
        vi = known_idiom_rendering(key, memory)
        if vi:
            known[key] = vi
        else:
            fresh[key] = _fresh_idiom_hint(key, memory, detector)
    return known, fresh


def _fresh_idiom_hint(key: str, memory: dict | None, detector: dict) -> str:
    """Goi y cho thanh ngu chua co cach dich: "gợi ý: ..." = cach dich cua buoc chuan bi
    (suy luan cao, theo IDIOM_PRIORITY_RULES) - dung duoc neu hop cau; "nghĩa: ..." = nghia
    tham khao (tu dien chung, ban dich truoc kieu cu) - chi de hieu, khong chep."""
    entry = (memory or {}).get(key) or {}
    if entry.get("source") == "chuan_bi" and entry.get("vi"):
        return "gợi ý: " + entry["vi"]
    meaning = entry.get("vi") or detector.get(key, "")
    return "nghĩa: " + meaning if meaning else ""


def build_terms_block(glossary: dict, known_idioms: dict | None = None,
                      fresh_idioms: dict | None = None) -> str:
    lines = [f"{zh} = {vi}" for zh, vi in glossary.items()]
    block = ("Glossary (Trung = Viet, BAT BUOC dung dung nguyen van):\n"
             + ("\n".join(lines) if lines else "(khong co)") + "\n")
    if known_idioms:
        block += ("\nThành ngữ đã có cách dịch (đã duyệt hoặc đã dùng ở chương trước) - dùng lại "
                  "đúng cách dịch này cho thống nhất, chỉ đổi khi ngữ cảnh thật sự khác:\n"
                  + "\n".join(f"{zh} = {vi}" for zh, vi in known_idioms.items()) + "\n")
    if fresh_idioms:
        block += ("\nThành ngữ mới trong chương - \"gợi ý\" là cách dịch soạn sẵn cho cả truyện: dùng "
                  "nếu hợp câu, không hợp thì tự chọn theo quy tắc 2; \"nghĩa\" chỉ để hiểu, KHÔNG chép "
                  "nguyên - hãy dùng thành ngữ/cách nói tương đương của người Việt:\n"
                  + "\n".join(f"{zh}: {m}" if m else zh for zh, m in fresh_idioms.items()) + "\n")
    return block


def clean_idioms(raw_idioms, chapter: dict, paragraphs: list[str], skip: dict | None = None) -> dict:
    """Loc truong "idioms" model tra ve {thanh_ngu_goc: cum_tieng_Viet_da_dung}. Chi giu khi
    thanh ngu co trong chuong VA cum tieng Viet thuc su nam trong ban dich (khong ghi lai
    cach dich model tu khai ma khong dung). Khoa tra ve la dang gian the."""
    if not isinstance(raw_idioms, dict):
        return {}
    text = _chapter_text(chapter)
    output = "\n".join(paragraphs).lower()
    skipped = {normalize_zh(k) for k in (skip or {})}
    out = {}
    for k, v in raw_idioms.items():
        key = normalize_zh(str(k).strip())
        vi = str(v).strip().strip("\"“”'")
        if not (3 <= len(key) <= 24) or not vi or len(vi) > 80:
            continue
        if not _CJK_RE.search(key) or _CJK_RE.search(vi) or vi.lower().startswith("nghĩa đen"):
            continue
        if key not in text or key in skipped or vi.lower() not in output:
            continue
        out[key] = vi
    return out


def merge_idioms(memory: dict, idioms: dict, chapter_idx: int | None) -> list[str]:
    """Ghi cach dich thanh ngu cua 1 chuong vao tu dien rieng cua truyen (sua truc tiep).
    Moi cach dich duoc dem so chuong da dung; cach dung nhieu nhat thanh cach dich chinh.
    Muc anh Ber da duyet (approved) khong bao gio bi doi. Tra ve thanh ngu lan dau co cach dich."""
    added = []
    for key, vi in idioms.items():
        entry = memory.setdefault(key, {"vi": "", "approved": False, "source": "dich"})
        if not entry.get("vi"):
            added.append(key)
        variants = entry.setdefault("variants", {})
        variants[vi] = variants.get(vi, 0) + 1
        entry["chapters"] = entry.get("chapters", 0) + 1
        if chapter_idx is not None:
            entry.setdefault("first", chapter_idx)
            entry["last"] = chapter_idx
        if not entry.get("approved"):
            best_vi, best_n = max(variants.items(), key=lambda kv: kv[1])
            if not entry.get("vi") or variants.get(entry["vi"], 0) < best_n:
                entry["vi"] = best_vi
    return added


def clean_new_terms(raw_terms, chapter: dict) -> dict:
    """Loc new_terms model tra ve: khoa phai la chu Han co trong chuong, gia tri la
    tieng Viet (khong con chu Han), do dai hop ly, va co it nhat 2 tu viet hoa (ten rieng:
    "Lưu Thiến", "khách sạn Thủy Thượng Nhân Gia"; loai "Nhà" cho 家裡 - viet hoa vi dau cau). Glossary
    bi ep dung nguyen van o moi chuong sau, nen tu thuong model tu y them (朋友圈 = "danh bạ"
    - dich sai, 拘禁 = "giam giữ") se lap lai loi mai; de model tu dich theo ngu canh."""
    if not isinstance(raw_terms, dict):
        return {}
    text = _chapter_text(chapter)
    out = {}
    for k, v in raw_terms.items():
        k, v = str(k).strip(), str(v).strip()
        if not k or not v or len(k) > 12 or len(v) > 60:
            continue
        if not _CJK_RE.search(k) or _CJK_RE.search(v):
            continue
        if normalize_zh(k) not in text or sum(w[:1].isupper() for w in v.split()) < 2:
            continue
        out[k] = v
    return out


def split_idiom_terms(new_terms: dict, idiom_memory: dict | None = None) -> tuple[dict, dict]:
    """Model (nhat la khi tat thinking) hay nhet thanh ngu vao "new_terms" thay vi "idioms".
    Tach cac khoa la thanh ngu da biet (tu dien nhan dien, danh sach tuyen, tu dien rieng
    cua truyen) sang idioms de khong bi ep cung vao glossary nhu ten rieng."""
    known = set(_idiom_detector()) | set(load_curated_idioms()) | set(idiom_memory or {})
    terms, idioms = {}, {}
    for zh, vi in new_terms.items():
        (idioms if normalize_zh(zh) in known else terms)[zh] = vi
    return terms, idioms


def merge_new_terms(glossary: dict, new_terms: dict) -> dict:
    """Them thuat ngu MOI vao glossary (sua truc tiep), KHONG BAO GIO ghi de muc da co -
    ke ca khi khac gian/phon the - de ten nhan vat khong bi doi giua chung truyen.
    Tra ve cac muc thuc su duoc them."""
    existing = {normalize_zh(k) for k in glossary}
    added = {}
    for zh, vi in new_terms.items():
        key = normalize_zh(zh)
        if key in existing:
            continue
        existing.add(key)
        added[zh] = vi
    glossary.update(added)
    return added


def check_term_usage(chapter: dict, paragraphs: list[str], terms: dict) -> list[tuple[str, str]]:
    """Kiem tra sau dich: muc glossary co trong ban goc thi ban dich phai chua dung
    ban dich co dinh. Cum ngan nam tron trong cum dai hon (vd ho 上官 trong 上官嫣红)
    duoc bo qua neu khong con xuat hien doc lap. Tra ve [(zh, vi)] bi thieu."""
    text = _chapter_text(chapter)
    output = "\n".join(paragraphs).lower()
    missing = []
    for zh in sorted(terms, key=lambda k: len(normalize_zh(k)), reverse=True):
        key = normalize_zh(zh)
        if key not in text:
            continue
        text = text.replace(key, "\0")
        if terms[zh].lower() not in output:
            missing.append((zh, terms[zh]))
    return missing


def _parse_sse_stream(response):
    """Doc SSE stream tu DeepSeek API, gop delta.content thanh chuoi day du.
    Bo qua reasoning_content (thinking) vi ta chi can ket qua cuoi.
    Tra ve (content, usage) - usage lay tu chunk cuoi (stream_options.include_usage)."""
    content_parts = []
    usage = None
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data.strip() == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            if chunk.get("usage"):
                usage = chunk["usage"]
            delta = chunk["choices"][0].get("delta", {})
            c = delta.get("content")
            if c:
                content_parts.append(c)
        except (json.JSONDecodeError, KeyError, IndexError):
            continue  # Bo qua chunk loi, doc tiep
    return "".join(content_parts), usage


def _parse_json_content(content: str) -> dict:
    """Parse JSON tu content API tra ve, co regex fallback khi JSON khong hop le."""
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        import re
        try:
            result = {}
            title_match = re.search(r'"title"\s*:\s*"([^"]+)"', content)
            if title_match: result["title"] = title_match.group(1)

            para_match = re.search(r'"paragraphs"\s*:\s*\[(.*?)\]', content, re.DOTALL)
            if para_match:
                paras_str = para_match.group(1)
                paras = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', paras_str)
                result["paragraphs"] = [p.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\') for p in paras]

            nn_match = re.search(r'"(?:new_names|new_terms)"\s*:\s*\{(.*?)\}', content, re.DOTALL)
            result["new_terms"] = {}
            if nn_match:
                pairs = re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', nn_match.group(1))
                for k, v in pairs: result["new_terms"][k] = v

            if "paragraphs" in result and result["paragraphs"]:
                return result
            raise e
        except Exception:
            raise e


def call_deepseek(system_prompt: str, user_prompt: str, api_key: str, model: str,
                   temperature: float, max_retries: int = 5, thinking: bool = False,
                   max_tokens: int = 4096, should_stop=None, on_usage=None,
                   reasoning_effort: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        # Do 2026-09/10 (deepseek-flash, json_object): tat thinking VAN dich duoc nhung kem
        # hon ro ret - thanh ngu dich sai/sat chu, sot chu Han (chuong 20-21: 3 tot/4 tam/7
        # sai so voi 11/3/0 khi bat thinking). Vi vay mac dinh LUON bat thinking cho cuoc
        # goi dich chuong - --no-thinking chi la lua chon danh doi chat luong lay toc do/gia.
        "thinking": {"type": "enabled" if thinking else "disabled"},
        # Model ho tro toi 384K token output nhung API mac dinh gioi han thap (~4096)
        # neu khong khai bao - 1 chuong tieu thuyet mang dai (VD >5000 chu Trung) dich
        # sang tieng Viet co the vuot 4096 token, khien JSON tra ve bi cat cut giua
        # chung -> json.loads() loi. Goi cho dich chuong truyen max_tokens cao hon
        # (xem translate_chapter), day chi la gia tri an toan mac dinh cho cac loi
        # goi khac (vd style-detect, luon ngan).
        "max_tokens": max_tokens,
    }
    # Muc do suy luan (low/medium/high/max; API quy medium ve high) - chi co nghia khi bat
    # thinking. None = mac dinh cua API (high). Token suy luan tinh gia output.
    if thinking and reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    # Tu dong bat streaming cho API call nang (translate_chapter) de tranh timeout.
    # Streaming cho phep moi chunk co read_timeout rieng (300s) thay vi gioi han
    # tong 180s cho toan bo response - chuong dai voi thinking co the mat 10-30 phut.
    use_stream = max_tokens > _STREAM_THRESHOLD
    if use_stream:
        payload["stream"] = True
        # Yeu cau API tra usage (prompt_tokens/completion_tokens) o chunk cuoi stream.
        payload["stream_options"] = {"include_usage": True}

    last_err = None
    for attempt in range(max_retries):
        if should_stop and should_stop():
            raise RuntimeError("Da dung theo yeu cau.")
        try:
            # Timeout: (connect, read). Streaming dung read_timeout per-chunk cao hon
            # vi moi chunk chi can den trong 300s (khong gioi han tong).
            timeout = (10, 300) if use_stream else (10, 180)
            resp = _SESSION.post(DEEPSEEK_API_URL, headers=headers, json=payload,
                                 timeout=timeout, stream=use_stream)

            if resp.status_code == 200:
                if use_stream:
                    content, usage = _parse_sse_stream(resp)
                else:
                    body = resp.json()
                    content = body["choices"][0]["message"]["content"]
                    usage = body.get("usage")

                if not content or not content.strip():
                    last_err = RuntimeError("API tra ve content rong")
                    time.sleep(min(2 ** attempt, 30))
                    continue

                if on_usage and usage:
                    on_usage(usage)
                return _parse_json_content(content)

            elif resp.status_code == 402:
                # Het so du tai khoan - khong retry, phat ngay
                try:
                    err_body = resp.json()
                    err_code = err_body.get("error", {}).get("code", "")
                    err_msg = err_body.get("error", {}).get("message", "")
                except Exception:
                    err_code, err_msg = "", resp.text[:200]
                raise InsufficientBalanceError(
                    f"HET SO DU TAI KHOAN DEEPSEEK (HTTP 402). "
                    f"Code: {err_code}. Msg: {err_msg}. "
                    f"Vui long nap them token tai platform.deepseek.com."
                )
            elif resp.status_code == 429 or resp.status_code >= 500:
                last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                resp.raise_for_status()
        except InsufficientBalanceError:
            raise  # Khong retry khi het so du
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
            last_err = e
        time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"DeepSeek API failed after {max_retries} attempts: {last_err}")


def detect_style_guide(chapters: list[dict], api_key: str, model: str,
                       should_stop=None) -> dict:
    """Phan tich van phong tu nhieu chuong nhau trong truyen."""
    sampled = sample_for_style(chapters)
    if not sampled:
        return {}
    parts = []
    for i, ch in enumerate(sampled):
        label = f"Chuong {i + 1}" + (f" ({ch['title']})" if ch.get("title") else "")
        body = "\n".join(ch["paragraphs"])
        parts.append(f"--- {label} ---\n{body}")
    user_prompt = "\n\n".join(parts)
    try:
        data = call_deepseek(STYLE_SYSTEM_PROMPT, user_prompt, api_key, model, temperature=1.0,
                              max_retries=3, thinking=True, max_tokens=8192,
                              should_stop=should_stop)
        return data
    except RuntimeError:
        return {}


def build_user_prompt(chapter: dict) -> str:
    paragraphs_json = json.dumps(chapter["paragraphs"], ensure_ascii=False)
    return (
        f"Du lieu chuong can dich (JSON):\n"
        f'{{"title": {json.dumps(chapter["title"], ensure_ascii=False)}, '
        f'"paragraphs": {paragraphs_json}}}'
    )


def translate_chapter(chapter: dict, system_prompt: str, api_key: str,
                       model: str, temperature: float, thinking: bool = True,
                       should_stop=None, chapter_idx: int | None = None,
                       log=print, glossary: dict | None = None,
                       reasoning_effort: str | None = None,
                       idiom_memory: dict | None = None) -> dict:
    """Dich 1 chuong. Neu truyen `glossary` (toan bo glossary cua truyen), chi cac muc
    co mat trong chuong + goi y thanh ngu cua chuong duoc noi vao CUOI system_prompt
    (phan dau prompt giu nguyen de van an cache). system_prompt khi do nen duoc tao voi
    glossary_block rong.

    Thanh ngu KHONG con bi thay cung bang tu dien truoc khi gui (ban cu ep ca nghia den
    "nghia den: ..." va cum tu thuong vao ban dich); gio chi gui nghia tham khao, model
    tu chon thanh ngu/cach noi Viet tuong duong. `idiom_memory` la tu dien thanh ngu rieng
    cua truyen: thanh ngu da co cach dich duoc goi y dung lai cho thong nhat."""
    chapter_terms: dict = {}
    if glossary is not None:
        chapter_terms = select_glossary_for_chapter(glossary, chapter)
        known, fresh = find_idioms_in_chapter(chapter, skip=chapter_terms, memory=idiom_memory)
        system_prompt = system_prompt + build_terms_block(chapter_terms, known, fresh)
        log(f"  Glossary chuong: {len(chapter_terms)} muc, thanh ngu da co cach dich: {len(known)}, "
            f"thanh ngu moi: {len(fresh)}")
    user_prompt = build_user_prompt(chapter)
    # max_tokens la tran chung cho CA reasoning_content LAN content khi thinking bat -
    # da kiem chung thuc te: voi 16384, 1 chuong ~70 doan bi reasoning "an" het tran
    # truoc khi kip sinh content, tra ve content rong -> json.loads("") loi "Expecting
    # value". Dat cao han han (con rat nho so tran 384K cua model, khong ton them phi
    # vi tinh theo token THUC TE sinh ra) de chua du reasoning cho chuong dai.
    usage: dict = {}

    def _log_usage(u):
        usage.update(u)
        details = u.get("completion_tokens_details") or {}
        log(f"[usage] prompt_tokens={u.get('prompt_tokens')} "
            f"(cache_hit={u.get('prompt_cache_hit_tokens')}, cache_miss={u.get('prompt_cache_miss_tokens')}) "
            f"completion_tokens={u.get('completion_tokens')} "
            f"(reasoning={details.get('reasoning_tokens')}) "
            f"total_tokens={u.get('total_tokens')}")

    result = call_deepseek(system_prompt, user_prompt, api_key, model, temperature,
                            thinking=thinking, max_tokens=131072, should_stop=should_stop,
                            on_usage=_log_usage, reasoning_effort=reasoning_effort)
    if chapter_idx is not None:
        title = f"Chương {chapter_idx}"
    else:
        title = postprocess_title(result.get("title", "")) if result.get("title") else chapter["title"]
    # Strip zero-width space markers (sau khi DeepSeek tra ve - co the con sot)
    raw_paragraphs = [p for p in result.get("paragraphs", []) if p and p.strip()]
    paragraphs = [postprocess(p).replace("\u200B", "") for p in raw_paragraphs]
    new_terms = clean_new_terms(result.get("new_terms") or result.get("new_names") or {}, chapter)
    new_terms, idioms_in_terms = split_idiom_terms(new_terms, idiom_memory)
    if len(paragraphs) != len(chapter["paragraphs"]):
        log(f"  CANH BAO: so doan dich {len(paragraphs)} != so doan goc {len(chapter['paragraphs'])}")
    leftover = [(i + 1, m) for i, p in enumerate(paragraphs) for m in _CJK_RUN_RE.findall(p)]
    if leftover:
        log(f"  CANH BAO: con sot chu Han chua dich: {leftover[:10]}")
    term_warnings = check_term_usage(chapter, paragraphs, chapter_terms)
    for zh, vi in term_warnings:
        log(f"  CANH BAO thuat ngu: '{zh}' phai dich la '{vi}' nhung khong thay trong ban dich")
    raw_idioms = result.get("idioms") if isinstance(result.get("idioms"), dict) else {}
    idioms = clean_idioms({**idioms_in_terms, **raw_idioms}, chapter, paragraphs, skip=chapter_terms)
    return {"title": title, "paragraphs": paragraphs, "new_terms": new_terms, "idioms": idioms,
            "term_warnings": [list(w) for w in term_warnings], "usage": usage}


def translate_novel(input_file: str, output_file: str, glossary_path: str | None, api_key: str,
                     model: str = DEFAULT_MODEL, temperature: float = 1.3, workers: int = 1,
                     thinking: bool = True, style_detect: bool = True, log=print,
                     on_chapter=None, should_stop=None, avoid_peak: bool = True,
                     on_balance_error=None, reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
                     prepare: bool = True) -> None:
    """Dich toan bo file da cao (input_file) sang output_file, resume duoc, tu cap nhat
    glossary_path khi phat hien ten moi. Dung chung cho CLI (main()), pipeline.py va GUI.
    glossary_path None/"" = glossary rieng cua truyen canh file dich (glossary_path_for).

    log: ham nhan 1 chuoi de bao tien do (mac dinh print; GUI truyen ham day vao log queue).
    on_chapter(idx, total, chapter_dict): goi sau moi chuong dich xong, de GUI cap nhat
        thanh progress bar/danh sach chuong thay vi phai parse chuoi log.
    should_stop: ham tra ve True neu can dung giua chung (GUI dung de xu ly nut "Dung").
    avoid_peak: mac dinh True - CAM goi API DeepSeek trong gio cao diem (9-12h, 14-18h
        gio Bac Kinh, thu 2-6 tru ngay le Trung Quoc, gia gap doi). Tu dong cho den khi het gio cao diem roi moi goi,
        kiem tra lai truoc MOI dot chuong (khong chi luc bat dau) vi 1 truyen dai co
        the dich xuyen qua luc bat dau/ket thuc gio cao diem.
    on_balance_error: ham duoc goi khi phat hien het so du tai khoan. Dung de bao hieu
        cho cac pipeline khac dung lai (trong multi-novel mode).
    prepare: mac dinh True - truoc khi dich, quet toan bo truyen da cao de lap glossary ten
        rieng va bang cach dich thanh ngu bang model suy luan cao (prepare_novel.py). Chi goi
        API cho ten/thanh ngu chua xet o lan chay truoc, nen chay lai gan nhu mien phi.
    """
    glossary_path = glossary_path or glossary_path_for(output_file)
    glossary = load_glossary(glossary_path)
    glossary_meta = load_glossary_meta(glossary_path)
    log(f"Glossary rieng cua truyen: {len(glossary)} ten ({glossary_path}).")

    chapters = parse_chapters(input_file)
    log(f"Da phan tich {len(chapters)} chuong tu {input_file}.")
    title_offset = 1 if is_novel_title_entry(chapters, 0) else 0

    done = count_translated_chapters(output_file)
    pending = chapters[done:]
    failed_chapters: list[dict] = []
    log(f"Da dich {done} chuong truoc do, con lai {len(pending)} chuong.")

    if not pending:
        log("Khong con gi de dich.")
        return

    if avoid_peak and wait_until_offpeak(log=log, should_stop=should_stop):
        return

    style_guide = ""
    term_categories = "các thuật ngữ đặc thù của truyện, thành ngữ, tục ngữ"
    style_file = output_file.rsplit('.', 1)[0] + "_style.txt" if '.' in output_file else output_file + "_style.txt"
    idiom_path = idioms_path_for(output_file)
    idiom_memory = load_idiom_memory(idiom_path)
    log(f"Da nap {len(idiom_memory)} thanh ngu tu {idiom_path}.")

    if style_detect:
        if os.path.exists(style_file):
            try:
                with open(style_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content.startswith("{"):
                    try:
                        style_data = json.loads(content)
                        style_guide = style_data.get("style_guide", "")
                        term_categories = style_data.get("term_categories", term_categories)
                    except Exception:
                        style_guide = content
                else:
                    style_guide = content
                log(f"Đã nạp văn phong từ {style_file}")
            except Exception as e:
                log(f"Lỗi khi đọc file văn phong: {e}")

        if not style_guide:
            log("Dang phan tich van phong tu nhieu chuong (dau/giua/cuoi)...")
            style_data = detect_style_guide(chapters, api_key, model, should_stop=should_stop)
            if isinstance(style_data, dict):
                style_guide = style_data.get("style_guide", "").strip()
                term_categories = style_data.get("term_categories", term_categories).strip()
            elif isinstance(style_data, str):
                style_guide = style_data.strip()

            log(f"Van phong xac dinh: {style_guide or '(khong xac dinh duoc, dung mac dinh)'}")
            if style_guide:
                try:
                    with open(style_file, "w", encoding="utf-8") as f:
                        json.dump({"style_guide": style_guide, "term_categories": term_categories}, f, ensure_ascii=False, indent=2)
                    log(f"Đã lưu văn phong vào {style_file}")
                except Exception as e:
                    log(f"Lỗi khi lưu file văn phong: {e}")

    if prepare:
        from prepare_novel import prepare_novel
        try:
            prepare_novel(chapters, output_file, glossary_path, api_key, model=model,
                          style_guide=style_guide, log=log, should_stop=should_stop)
        except InsufficientBalanceError:
            raise
        except Exception as e:  # buoc chuan bi hong khong duoc chan viec dich
            log(f"[Chuan bi] Loi, bo qua buoc chuan bi: {e}")
        if should_stop and should_stop():
            return
        glossary = load_glossary(glossary_path)
        idiom_memory = load_idiom_memory(idiom_path)
        log(f"Sau buoc chuan bi: {len(glossary)} ten, {len(idiom_memory)} thanh ngu.")

    def build_system_prompt(current_style, current_term_cats):
        # Glossary + thanh ngu duoc translate_chapter noi vao cuoi prompt theo tung chuong.
        style_block = f"Van phong ap dung cho toan truyen: {current_style}\n" if current_style else ""
        return TRANSLATE_SYSTEM_PROMPT.format(
            style_guide_block=style_block,
            term_categories=current_term_cats,
            glossary_block=""
        )

    system_prompt = build_system_prompt(style_guide, term_categories)
    last_style_eval_idx = done

    if workers > 1:
        log(f"CANH BAO: workers={workers} - nhieu chapter dich song song co the lam mat nhat quan ten rieng.")

    def _work(ch, chapter_idx, glossary_snapshot, idiom_snapshot):
        if is_novel_title_entry(chapters, chapter_idx - 1):
            return {"title": ch["title"], "paragraphs": [], "new_terms": {}, "idioms": {},
                    "term_warnings": [], "usage": {}}
        # Kiem tra write-ahead cache truoc khi goi API
        cached = _load_cache(output_file, chapter_idx)
        if cached is not None:
            log(f"[{chapter_idx}/{len(chapters)}] Cache hit - bo qua API call")
            return cached
        result = translate_chapter(ch, system_prompt, api_key, model,
                                  temperature, thinking=thinking, should_stop=should_stop,
                                  chapter_idx=chapter_idx - title_offset, log=log, glossary=glossary_snapshot,
                                  reasoning_effort=reasoning_effort, idiom_memory=idiom_snapshot)
        # Ghi write-ahead cache ngay khi API tra ve thanh cong
        _save_cache(output_file, chapter_idx, result)
        return result

    # Nop theo tung dot toi da `workers` chuong (khong dung executor.map()): map() nop
    # HET pending ngay lap tuc bat ke so worker, nen bam "Dung" van khong ngan duoc cac
    # chuong da nam san trong hang doi - tiep tuc chay ngam va tinh phi API. Nop theo
    # dot dam bao sau khi dung, toi da chi con `workers` chuong dang chay dot (voi
    # workers=1 mac dinh, dung ngay lap tuc sau chuong dang dich).
    stopped = False
    with open(output_file, "a", encoding="utf-8") as f_out:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for batch_start in range(0, len(pending), workers):
                if avoid_peak and wait_until_offpeak(log=log, should_stop=should_stop):
                    stopped = True
                    break
                
                current_idx = done + batch_start + 1
                if style_detect and current_idx - last_style_eval_idx >= 200:
                    log(f"Đã qua {current_idx - last_style_eval_idx} chương, đang tái đánh giá văn phong cho arc mới...")
                    recent_chapters = chapters[max(0, current_idx-30):current_idx+30]
                    style_data = detect_style_guide(recent_chapters, api_key, model, should_stop=should_stop)
                    new_style = style_data.get("style_guide", "").strip() if isinstance(style_data, dict) else (style_data.strip() if isinstance(style_data, str) else "")
                    new_term_cats = style_data.get("term_categories", "").strip() if isinstance(style_data, dict) else ""
                    if new_style:
                        style_guide = new_style
                        if new_term_cats:
                            term_categories = new_term_cats
                        system_prompt = build_system_prompt(style_guide, term_categories)
                        log(f"Văn phong mới cập nhật: {style_guide}")
                        try:
                            with open(style_file, "w", encoding="utf-8") as f:
                                json.dump({"style_guide": style_guide, "term_categories": term_categories}, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                    last_style_eval_idx = current_idx

                batch = pending[batch_start:batch_start + workers]
                # Ban sao glossary cho ca dot: luong chinh con them thuat ngu moi trong khi
                # cac worker khac cung dot van dang doc.
                glossary_snapshot = dict(glossary)
                idiom_snapshot = dict(idiom_memory)
                futures = [executor.submit(_work, ch, done + batch_start + offset + 1,
                                           glossary_snapshot, idiom_snapshot)
                           for offset, ch in enumerate(batch)]
                batch_failed = False
                for offset, (ch, fut) in enumerate(zip(batch, futures)):
                    idx = done + batch_start + offset + 1
                    try:
                        translated = fut.result()
                    except InsufficientBalanceError as e:
                        log(f"\n{'='*60}")
                        log(f"[!!! HET SO DU API !!!] {e}")
                        log(f"{'='*60}")
                        if on_balance_error:
                            on_balance_error(str(e))
                        failed_chapters.append({"index": idx, "title": ch["title"], "error": str(e)})
                        stopped = True
                        batch_failed = True
                        break
                    except Exception as e:
                        log(f"[{idx}/{len(chapters)}] LOI chapter '{ch['title']}': {type(e).__name__}: {e}")
                        failed_chapters.append({"index": idx, "title": ch["title"], "error": str(e)})
                        if on_chapter:
                            on_chapter(idx, len(chapters), None)
                        batch_failed = True
                        break  # Bao toan thu tu, khong xuat cac future sau


                    if is_novel_title_entry(chapters, idx - 1):
                        translated["title"] = ch["title"]
                    else:
                        translated["title"] = f"Chương {idx - title_offset}"
                    f_out.write(f"=== {translated['title']} ===\n\n")
                    for p in translated["paragraphs"]:
                        f_out.write(f"{p}\n\n")
                    f_out.write(CHAPTER_SEP)
                    f_out.flush()
                    # Ghi file chinh thanh cong -> xoa cache
                    _delete_cache(output_file, idx)

                    added = merge_new_terms(glossary, translated["new_terms"])
                    actual_new_count = len(added)
                    if added:
                        save_glossary(glossary_path, glossary)
                        glossary_meta = update_glossary_meta(glossary_meta, added, idx)
                        save_glossary_meta(glossary_path, glossary_meta)
                    idioms_added = merge_idioms(idiom_memory, translated.get("idioms") or {}, idx)
                    if translated.get("idioms"):
                        save_idiom_memory(idiom_path, idiom_memory)

                    log(f"[{idx}/{len(chapters)}] {ch['title']} -> {translated['title']}"
                        + (f" (+{actual_new_count} thuat ngu moi)" if actual_new_count > 0 else "")
                        + (f" (+{len(idioms_added)} thanh ngu moi)" if idioms_added else ""))

                    if on_chapter:
                        on_chapter(idx, len(chapters), translated)
                
                # Cleanup glossary meta
                if not batch_failed:
                    glossary_meta, removed = cleanup_glossary_meta(
                        glossary_meta, done + batch_start + len(batch))
                    if removed:
                        save_glossary_meta(glossary_path, glossary_meta)

                if should_stop and should_stop():
                    log("Da dung theo yeu cau. Chay lai se tu tiep tuc tu day.")
                    stopped = True
                    break
                if batch_failed:
                    log("Phien dich tam dung do co chuong bi loi. De dam bao thu tu, vui long chay lai (Resume).")
                    stopped = True
                    break

    if failed_chapters:
        log(f"\nThanh cong: {len(chapters) - len(failed_chapters)}/{len(chapters)} chuong.")
        log(f"That bai {len(failed_chapters)} chuong:")
        for fc in failed_chapters:
            log(f"  - Chuong {fc['index']}: {fc['title']} | {fc['error']}")
    elif not stopped:
        log("Hoan tat dich thuat!")
        _clear_cache(output_file)
    return failed_chapters


def translate_novel_stream(chapter_generator, output_file: str, glossary_path: str | None,
                            api_key: str, model: str = DEFAULT_MODEL,
                            temperature: float = 1.3, thinking: bool = True,
                            style_guide: str = "", log=print,
                            on_chapter=None, should_stop=None,
                            on_balance_error=None, term_categories: str = "các thuật ngữ đặc thù của truyện, thành ngữ, tục ngữ",
                            reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
                            avoid_peak: bool = True) -> list[dict]:
    """Dich tung chuong tu generator (crawl_chapters_stream) ngay lap tuc khi co du lieu.

    Khac voi translate_novel (doc tu file co san), ham nay nhan chapter_generator -
    mot generator yield dict chuong ngay sau khi crao. Dich xong tung chuong, ghi ket
    qua vao output_file luon, khong doi den khi cao xong toan bo.

    Ung dung: pipeline --stream --chapters X: cao X chuong roi dich luon tung chuong.
    style_guide: truyen thang tu ket qua detect_style_guide neu da phan tich truoc do.
    avoid_peak: mac dinh True - cho het gio cao diem truoc moi chuong (nhu translate_novel).
    """
    glossary_path = glossary_path or glossary_path_for(output_file)
    glossary = load_glossary(glossary_path)
    glossary_meta = load_glossary_meta(glossary_path)
    log(f"Glossary rieng cua truyen: {len(glossary)} ten ({glossary_path}).")
    log("Che do stream: bo qua buoc chuan bi (chua cao du truyen), ten/thanh ngu hoc dan khi dich.")
    idiom_path = idioms_path_for(output_file)
    idiom_memory = load_idiom_memory(idiom_path)

    # Lay so chuong da dich truoc do de tinh idx tuong doi
    from crawler import count_chapters as _count
    already_done = _count(output_file)
    if already_done == 0:
        # File tho cua crawler luon co muc tieu de o dau; ghi muc do vao file dich truoc de
        # che do stream va che do thuong dung chung chi so (doi che do giua chung khong lech).
        with open(output_file, "a", encoding="utf-8") as f_head:
            f_head.write("=== TRUYỆN ===\n\n" + CHAPTER_SEP)
        already_done = 1
    title_offset = 1 if is_novel_title_entry(parse_chapters(output_file), 0) else 0
    log(f"Da dich {already_done - title_offset} chuong truoc do, bat dau ghi tiep.")

    style_block = f"Van phong ap dung cho toan truyen: {style_guide}\n" if style_guide else ""
    system_prompt = TRANSLATE_SYSTEM_PROMPT.format(
        style_guide_block=style_block,
        term_categories=term_categories,
        glossary_block=""
    )

    failed_chapters: list[dict] = []
    idx = already_done

    with open(output_file, "a", encoding="utf-8") as f_out:
        for chapter in chapter_generator:
            if should_stop and should_stop():
                log("Da dung theo yeu cau.")
                break

            if avoid_peak and wait_until_offpeak(log=log, should_stop=should_stop):
                break  # nguoi dung dung luc dang cho het gio cao diem

            idx += 1

            # Kiem tra write-ahead cache
            cached = _load_cache(output_file, idx)
            if cached is not None:
                log(f"[{idx}] Cache hit - bo qua API call")
                translated = cached
            else:
                try:
                    translated = translate_chapter(
                        chapter, system_prompt, api_key, model,
                        temperature, thinking=thinking, should_stop=should_stop,
                        chapter_idx=idx - title_offset, log=log, glossary=glossary,
                        reasoning_effort=reasoning_effort, idiom_memory=idiom_memory
                    )
                    # Ghi write-ahead cache ngay khi API tra ve thanh cong
                    _save_cache(output_file, idx, translated)
                except InsufficientBalanceError as e:
                    log(f"\n{'='*60}")
                    log(f"[!!! HET SO DU API !!!] {e}")
                    log(f"{'='*60}")
                    if on_balance_error:
                        on_balance_error(str(e))
                    failed_chapters.append({"index": idx, "title": chapter["title"], "error": str(e)})
                    break
                except Exception as e:
                    log(f"[{idx}] LOI dich '{chapter['title']}': {type(e).__name__}: {e}")
                    failed_chapters.append({"index": idx, "title": chapter["title"], "error": str(e)})
                    continue

            translated["title"] = f"Chương {idx - title_offset}"  # ghi de ca ket qua cache cu
            f_out.write(f"=== {translated['title']} ===\n\n")
            for p in translated["paragraphs"]:
                f_out.write(f"{p}\n\n")
            f_out.write(CHAPTER_SEP)
            f_out.flush()
            # Ghi file chinh thanh cong -> xoa cache
            _delete_cache(output_file, idx)

            added = merge_new_terms(glossary, translated["new_terms"])
            actual_new_count = len(added)
            if added:
                save_glossary(glossary_path, glossary)
                glossary_meta = update_glossary_meta(glossary_meta, added, idx)
                save_glossary_meta(glossary_path, glossary_meta)
            idioms_added = merge_idioms(idiom_memory, translated.get("idioms") or {}, idx)
            if translated.get("idioms"):
                save_idiom_memory(idiom_path, idiom_memory)

            log(f"[{idx}] [Dich] {chapter['title']} -> {translated['title']}"
                + (f" (+{actual_new_count} thuat ngu moi)" if actual_new_count > 0 else "")
                + (f" (+{len(idioms_added)} thanh ngu moi)" if idioms_added else ""))

            if on_chapter:
                on_chapter(idx, None, translated)

            # Cleanup meta moi 20 chuong
            if idx % 20 == 0:
                glossary_meta, removed = cleanup_glossary_meta(glossary_meta, idx)
                if removed:
                    save_glossary_meta(glossary_path, glossary_meta)

    if failed_chapters:
        log(f"That bai {len(failed_chapters)} chuong trong luot stream nay.")
    return failed_chapters


def main():

    parser = argparse.ArgumentParser(description="Dich truyen da cao sang tieng Viet bang DeepSeek API")
    parser.add_argument("--input", default="truyen_de_tam_trung_nhan_cach.txt")
    parser.add_argument("--output", default="truyen_de_tam_trung_nhan_cach_viet_deepseek.txt")
    parser.add_argument("--glossary", default=None,
                         help="Mac dinh: glossary rieng cua truyen canh file dich (<file dich>_glossary.json)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=1.3,
                         help="DeepSeek khuyen nghi 1.3 cho dich thuat")
    parser.add_argument("--workers", type=int, default=1,
                         help="So chuong dich song song (>1 danh doi tinh nhat quan ten rieng lay toc do)")
    parser.add_argument("--no-style-detect", action="store_true",
                         help="Bo qua buoc tu phan tich van phong tu chuong dau")
    parser.add_argument("--no-thinking", action="store_true",
                         help="Tat thinking mode cho tung chuong dich de tiet kiem token/chi phi. "
                              "CANH BAO: thinking tat van dich duoc nhung chat luong kem hon, de sot thanh ngu "
                              "va chu Han.")
    parser.add_argument("--reasoning-effort", choices=REASONING_EFFORTS, default=DEFAULT_REASONING_EFFORT,
                         help="Muc suy luan khi bat thinking (mac dinh: medium, API quy ve high). 'low' re "
                              "hon ~15%% nhung dich thanh ngu kem hon.")
    parser.add_argument("--no-prepare", action="store_true",
                         help="Bo qua buoc chuan bi (quet ca truyen lap glossary ten + thanh ngu truoc khi dich)")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--allow-peak", action="store_true",
                         help="Cho phep goi API trong gio cao diem DeepSeek (9-12h, 14-18h gio Bac Kinh, "
                              "thu 2-6 tru ngay le Trung Quoc, gia gap doi) - mac dinh KHONG cho phep, tu dong "
                              "cho het gio cao diem")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    load_dotenv(args.env_file)
    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print(f"Error: thieu DEEPSEEK_API_KEY (dat trong {args.env_file}, bien moi truong, hoac --api-key).")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: khong tim thay file input {args.input}. Chay crawler.py truoc.")
        sys.exit(1)

    translate_novel(args.input, args.output, args.glossary, api_key, model=args.model,
                     temperature=args.temperature, workers=args.workers, thinking=not args.no_thinking,
                     style_detect=not args.no_style_detect, avoid_peak=not args.allow_peak,
                     reasoning_effort=args.reasoning_effort, prepare=not args.no_prepare)


if __name__ == "__main__":
    main()
