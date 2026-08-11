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
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from crawler import CHAPTER_SEP, count_chapters, parse_chapters
from text_postprocess import postprocess, postprocess_title

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
# Giu ten cu de tuong thich nguoc voi code/test da import truoc do.
count_translated_chapters = count_chapters


class InsufficientBalanceError(RuntimeError):
    """Tai khoan DeepSeek het so du, khong the tiep tuc goi API."""
    pass

# Gio cao diem DeepSeek: gia gap doi 9h-12h va 14h-18h GIO BAC KINH (UTC+8) moi ngay.
# Trung Quoc khong dung DST nen offset co dinh, khong can zoneinfo/tzdata.
BEIJING_TZ = timezone(timedelta(hours=8))
PEAK_WINDOWS_BEIJING = [(9, 12), (14, 18)]  # [start, end) gio, dang 24h


def is_peak_hour(now: datetime | None = None) -> bool:
    now = now or datetime.now(BEIJING_TZ)
    h = now.astimezone(BEIJING_TZ).hour
    return any(start <= h < end for start, end in PEAK_WINDOWS_BEIJING)


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

TRANSLATE_SYSTEM_PROMPT = """Ban la dich gia tieu thuyet mang chuyen nghiep, dich Trung -> Viet.
{style_guide_block}
Yeu cau bat buoc:
1. Dich tu nhien, dung van phong da xac dinh o tren, loi thoai song dong, khong dich
   tung chu mot cach may moc, khong Han-Viet hoa nhung cho khong can thiet.
2. Dung CHINH XAC ban thuat ngu (glossary) duoc cung cap cho ten nhan vat/dia danh/
   thuat ngu rieng, ap dung xuyen suot de dam bao tinh nhat quan giua cac chuong.
3. Neu gap ten nhan vat/dia danh, va {term_categories} CHUA co trong glossary, hay CHON MOT
   CACH DICH CO DINH duy nhat cho no va liet ke vao truong "new_terms" de dung lai
   cho cac chuong sau - khong duoc dich cung mot ten theo nhieu cach khac nhau.
4. Giu nguyen so luong doan van dung bang so luong trong "paragraphs" dau vao,
   KHONG gop, KHONG tach, KHONG bo sot doan nao.
5. Khong them loi binh, khong them chu thich, khong dich thua noi dung khong co.
6. Dau ra phai la VAN BAN THUAN (plain text) cho tung doan, KHONG dung markdown,
   KHONG dung the HTML - vi ban dich se duoc dong goi thang vao EPUB.
7. Tra loi DUY NHAT bang JSON hop le theo dung schema:
   {{"title": "tieu de da dich", "paragraphs": ["doan 1 da dich", ...],
     "new_terms": {{"tu_trung_moi": "tu_viet_co_dinh"}}}}

Viec dich TIEU DE CHUONG:
- Neu tieu de goc co chua so chuong (vi du: "第1章", "第01章", "第十一回"...), bat buoc phai giu lai va dich dong nhat sang tieng Viet theo dinh dang "Chương X: [Ten chuong]" (vi du: "Chương 1: Dai bien hoat nhan").
- Tieu de chuong ngan gon (2-8 tu), mang tinh thanh ngu/ngu co, truc dac.
- KHONG dich dai nhu cau van, KHONG them chu thich, KHONG viet hoa cau.
- Uu tien cach dich goi am, ngan gon, de nho. VD: "一念永恒" -> "Nhat niem vinh hang",
  "Thien dao vo than" -> "Thien dao vo than", "Phuc sinh" -> "Phuc sinh".
- Giu nguyen phong cach cua tieu de goc (neu goc ngan thi dich cung ngan).
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
        json.dump(glossary, f, ensure_ascii=False, indent=2, sort_keys=True)


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
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


def cleanup_glossary_meta(meta: dict, current_chapter: int, max_idle_chapters: int = 100) -> dict:
    """Loai bo thuat ngu it dung (count=1) va khong xuat hien lau de nhe RAM."""
    keys_to_delete = []
    for zh, m in meta.items():
        if m.get("count", 1) == 1 and (current_chapter - m.get("last_seen", current_chapter)) > max_idle_chapters:
            keys_to_delete.append(zh)
    for k in keys_to_delete:
        del meta[k]
    return meta


def update_glossary_meta(meta: dict, new_names: dict, chapter_idx: int) -> dict:
    """Cap nhat metadata cho cac entry moi/da co."""
    for zh, vi in new_names.items():
        if zh in meta:
            meta[zh]["last_seen"] = chapter_idx
            meta[zh]["count"] = meta[zh].get("count", 0) + 1
        else:
            meta[zh] = {"last_seen": chapter_idx, "count": 1}
    return meta


def filter_glossary(glossary: dict, meta: dict, current_chapter: int,
                     max_entries: int = 50, recent_window: int = 50) -> dict:
    """Loc glossary chi gui nhung entry quan trong (gan day hoac tan suat cao)."""
    if not meta or len(glossary) <= max_entries:
        return glossary

    scored: list[tuple[float, str, str]] = []
    for zh, vi in glossary.items():
        m = meta.get(zh, {})
        last = m.get("last_seen", 0)
        count = m.get("count", 1)
        recency = 1.0 if (current_chapter - last) <= recent_window else 0.0
        # Diem: recency (0/1) + tan suat (0-1 normalize)
        score = recency * 2.0 + min(count / 20.0, 1.0)
        scored.append((score, zh, vi))

    scored.sort(reverse=True)
    return {zh: vi for _, zh, vi in scored[:max_entries]}


def call_deepseek(system_prompt: str, user_prompt: str, api_key: str, model: str,
                   temperature: float, max_retries: int = 5, thinking: bool = False,
                   max_tokens: int = 4096, should_stop=None) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        # QUAN TRONG: da kiem chung thuc te - voi response_format=json_object, neu tat
        # thinking thi deepseek-v4-flash chi ECHO nguyen van doan Trung vao truong
        # "paragraphs" thay vi dich (0% dich duoc), do system prompt yeu cau dich ro
        # rang. Bat thinking thi dich dung binh thuong (co reasoning_content chung
        # minh model thuc su suy luan dich tung cau). Vi vay mac dinh LUON bat thinking
        # cho cuoc goi dich chuong - --no-thinking chi de danh khi API/model doi hanh vi.
        "thinking": {"type": "enabled" if thinking else "disabled"},
        # Model ho tro toi 384K token output nhung API mac dinh gioi han thap (~4096)
        # neu khong khai bao - 1 chuong tieu thuyet mang dai (VD >5000 chu Trung) dich
        # sang tieng Viet co the vuot 4096 token, khien JSON tra ve bi cat cut giua
        # chung -> json.loads() loi. Goi cho dich chuong truyen max_tokens cao hon
        # (xem translate_chapter), day chi la gia tri an toan mac dinh cho cac loi
        # goi khac (vd style-detect, luon ngan).
        "max_tokens": max_tokens,
    }
    last_err = None
    for attempt in range(max_retries):
        if should_stop and should_stop():
            raise RuntimeError("Da dung theo yeu cau.")
        try:
            resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    import re
                    try:
                        # Regex fallback for malformed JSON
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


def build_user_prompt(chapter: dict, glossary: dict) -> str:
    glossary_lines = "\n".join(f"{zh} = {vi}" for zh, vi in glossary.items())
    paragraphs_json = json.dumps(chapter["paragraphs"], ensure_ascii=False)
    return (
        f"Glossary (Trung = Viet, dung co dinh):\n{glossary_lines or '(khong co)'}\n\n"
        f"Du lieu chuong can dich (JSON):\n"
        f'{{"title": {json.dumps(chapter["title"], ensure_ascii=False)}, '
        f'"paragraphs": {paragraphs_json}}}'
    )


def translate_chapter(chapter: dict, glossary: dict, system_prompt: str, api_key: str,
                       model: str, temperature: float, thinking: bool = True,
                       should_stop=None, chapter_idx: int | None = None) -> dict:
    user_prompt = build_user_prompt(chapter, glossary)
    # max_tokens la tran chung cho CA reasoning_content LAN content khi thinking bat -
    # da kiem chung thuc te: voi 16384, 1 chuong ~70 doan bi reasoning "an" het tran
    # truoc khi kip sinh content, tra ve content rong -> json.loads("") loi "Expecting
    # value". Dat cao han han (con rat nho so tran 384K cua model, khong ton them phi
    # vi tinh theo token THUC TE sinh ra) de chua du reasoning cho chuong dai.
    result = call_deepseek(system_prompt, user_prompt, api_key, model, temperature,
                            thinking=thinking, max_tokens=131072, should_stop=should_stop)
    if chapter_idx is not None:
        title = f"Chương {chapter_idx}"
    else:
        title = postprocess_title(result.get("title", "")) if result.get("title") else chapter["title"]
    paragraphs = [postprocess(p) for p in result.get("paragraphs", []) if p and p.strip()]
    new_terms = {}
    extracted_terms = result.get("new_terms") or result.get("new_names") or {}
    if isinstance(extracted_terms, dict):
        new_terms = {
            str(k).strip(): str(v).strip()
            for k, v in extracted_terms.items()
            if str(k).strip() and str(v).strip()
        }
    return {"title": title, "paragraphs": paragraphs, "new_terms": new_terms}


def translate_novel(input_file: str, output_file: str, glossary_path: str, api_key: str,
                     model: str = "deepseek-v4-flash", temperature: float = 1.3, workers: int = 1,
                     thinking: bool = True, style_detect: bool = True, log=print,
                     on_chapter=None, should_stop=None, avoid_peak: bool = True,
                     on_balance_error=None) -> None:
    """Dich toan bo file da cao (input_file) sang output_file, resume duoc, tu cap nhat
    glossary_path khi phat hien ten moi. Dung chung cho CLI (main()), pipeline.py va GUI.

    log: ham nhan 1 chuoi de bao tien do (mac dinh print; GUI truyen ham day vao log queue).
    on_chapter(idx, total, chapter_dict): goi sau moi chuong dich xong, de GUI cap nhat
        thanh progress bar/danh sach chuong thay vi phai parse chuoi log.
    should_stop: ham tra ve True neu can dung giua chung (GUI dung de xu ly nut "Dung").
    avoid_peak: mac dinh True - CAM goi API DeepSeek trong gio cao diem (9-12h, 14-18h
        gio Bac Kinh, gia gap doi). Tu dong cho den khi het gio cao diem roi moi goi,
        kiem tra lai truoc MOI dot chuong (khong chi luc bat dau) vi 1 truyen dai co
        the dich xuyen qua luc bat dau/ket thuc gio cao diem.
    on_balance_error: ham duoc goi khi phat hien het so du tai khoan. Dung de bao hieu
        cho cac pipeline khac dung lai (trong multi-novel mode).
    """
    glossary = load_glossary(glossary_path)
    glossary_meta = load_glossary_meta(glossary_path)
    log(f"Da nap {len(glossary)} thuat ngu tu {glossary_path}.")

    chapters = parse_chapters(input_file)
    log(f"Da phan tich {len(chapters)} chuong tu {input_file}.")

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

    style_block = f"Van phong ap dung cho toan truyen: {style_guide}\n" if style_guide else ""
    system_prompt = TRANSLATE_SYSTEM_PROMPT.format(style_guide_block=style_block, term_categories=term_categories)
    last_style_eval_idx = done

    if workers > 1:
        log(f"CANH BAO: workers={workers} - nhieu chapter dich song song co the lam mat nhat quan ten rieng.")

    def _work(ch, chapter_idx):
        filtered = filter_glossary(glossary, glossary_meta, chapter_idx)
        return translate_chapter(ch, filtered, system_prompt, api_key, model,
                                  temperature, thinking=thinking, should_stop=should_stop,
                                  chapter_idx=chapter_idx)

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
                        style_block = f"Van phong ap dung cho toan truyen: {style_guide}\n"
                        system_prompt = TRANSLATE_SYSTEM_PROMPT.format(style_guide_block=style_block, term_categories=term_categories)
                        log(f"Văn phong mới cập nhật: {style_guide}")
                        try:
                            with open(style_file, "w", encoding="utf-8") as f:
                                json.dump({"style_guide": style_guide, "term_categories": term_categories}, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                    last_style_eval_idx = current_idx

                batch = pending[batch_start:batch_start + workers]
                futures = [executor.submit(_work, ch, done + batch_start + offset + 1)
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


                    f_out.write(f"=== {translated['title']} ===\n\n")
                    for p in translated["paragraphs"]:
                        f_out.write(f"{p}\n\n")
                    f_out.write(CHAPTER_SEP)
                    f_out.flush()

                    actual_new_count = 0
                    if translated["new_terms"]:
                        actual_new_count = sum(1 for k in translated["new_terms"] if k not in glossary)
                        glossary.update(translated["new_terms"])
                        save_glossary(glossary_path, glossary)
                        glossary_meta = update_glossary_meta(glossary_meta, translated["new_terms"], idx)
                        save_glossary_meta(glossary_path, glossary_meta)

                    log(f"[{idx}/{len(chapters)}] {ch['title']} -> {translated['title']}"
                        + (f" (+{actual_new_count} thuat ngu moi)" if actual_new_count > 0 else ""))

                    if on_chapter:
                        on_chapter(idx, len(chapters), translated)
                
                # Cleanup glossary meta
                if not batch_failed:
                    glossary_meta = cleanup_glossary_meta(glossary_meta, done + batch_start + len(batch))
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
    return failed_chapters


def translate_novel_stream(chapter_generator, output_file: str, glossary_path: str,
                            api_key: str, model: str = "deepseek-v4-flash",
                            temperature: float = 1.3, thinking: bool = True,
                            style_guide: str = "", log=print,
                            on_chapter=None, should_stop=None,
                            on_balance_error=None, term_categories: str = "các thuật ngữ đặc thù của truyện, thành ngữ, tục ngữ") -> list[dict]:
    """Dich tung chuong tu generator (crawl_chapters_stream) ngay lap tuc khi co du lieu.

    Khac voi translate_novel (doc tu file co san), ham nay nhan chapter_generator -
    mot generator yield dict chuong ngay sau khi crao. Dich xong tung chuong, ghi ket
    qua vao output_file luon, khong doi den khi cao xong toan bo.

    Ung dung: pipeline --stream --chapters X: cao X chuong roi dich luon tung chuong.
    style_guide: truyen thang tu ket qua detect_style_guide neu da phan tich truoc do.
    """
    glossary = load_glossary(glossary_path)
    glossary_meta = load_glossary_meta(glossary_path)
    log(f"Da nap {len(glossary)} thuat ngu tu {glossary_path}.")

    # Lay so chuong da dich truoc do de tinh idx tuong doi
    from crawler import count_chapters as _count
    already_done = _count(output_file)
    log(f"Da dich {already_done} chuong truoc do, bat dau ghi tiep.")

    style_block = f"Van phong ap dung cho toan truyen: {style_guide}\n" if style_guide else ""
    system_prompt = TRANSLATE_SYSTEM_PROMPT.format(style_guide_block=style_block)

    failed_chapters: list[dict] = []
    idx = already_done

    with open(output_file, "a", encoding="utf-8") as f_out:
        for chapter in chapter_generator:
            if should_stop and should_stop():
                log("Da dung theo yeu cau.")
                break

            idx += 1
            filtered = filter_glossary(glossary, glossary_meta, idx)
            try:
                translated = translate_chapter(
                    chapter, filtered, system_prompt, api_key, model,
                    temperature, thinking=thinking, should_stop=should_stop,
                    chapter_idx=idx
                )
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

            f_out.write(f"=== {translated['title']} ===\n\n")
            for p in translated["paragraphs"]:
                f_out.write(f"{p}\n\n")
            f_out.write(CHAPTER_SEP)
            f_out.flush()

            actual_new_count = 0
            if translated["new_terms"]:
                actual_new_count = sum(1 for k in translated["new_terms"] if k not in glossary)
                glossary.update(translated["new_terms"])
                save_glossary(glossary_path, glossary)
                glossary_meta = update_glossary_meta(glossary_meta, translated["new_terms"], idx)
                save_glossary_meta(glossary_path, glossary_meta)

            log(f"[{idx}] [Dich] {chapter['title']} -> {translated['title']}"
                + (f" (+{actual_new_count} thuat ngu moi)" if actual_new_count > 0 else ""))

            if on_chapter:
                on_chapter(idx, None, translated)

            # Cleanup meta moi 20 chuong
            if idx % 20 == 0:
                glossary_meta = cleanup_glossary_meta(glossary_meta, idx)
                save_glossary_meta(glossary_path, glossary_meta)

    if failed_chapters:
        log(f"That bai {len(failed_chapters)} chuong trong luot stream nay.")
    return failed_chapters


def main():

    parser = argparse.ArgumentParser(description="Dich truyen da cao sang tieng Viet bang DeepSeek API")
    parser.add_argument("--input", default="truyen_de_tam_trung_nhan_cach.txt")
    parser.add_argument("--output", default="truyen_de_tam_trung_nhan_cach_viet_deepseek.txt")
    parser.add_argument("--glossary", default="glossary.json")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--temperature", type=float, default=1.3,
                         help="DeepSeek khuyen nghi 1.3 cho dich thuat")
    parser.add_argument("--workers", type=int, default=1,
                         help="So chuong dich song song (>1 danh doi tinh nhat quan ten rieng lay toc do)")
    parser.add_argument("--no-style-detect", action="store_true",
                         help="Bo qua buoc tu phan tich van phong tu chuong dau")
    parser.add_argument("--no-thinking", action="store_true",
                         help="Tat thinking mode cho tung chuong dich de tiet kiem token/chi phi. "
                              "CANH BAO: da kiem chung deepseek-v4-flash voi response_format=json_object "
                              "+ thinking tat se KHONG dich, chi echo nguyen van dau vao - chi dung co nay "
                              "neu model/API doi khac hanh vi nay.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--allow-peak", action="store_true",
                         help="Cho phep goi API trong gio cao diem DeepSeek (9-12h, 14-18h gio Bac Kinh, "
                              "gia gap doi) - mac dinh KHONG cho phep, tu dong cho het gio cao diem")
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
                     style_detect=not args.no_style_detect, avoid_peak=not args.allow_peak)


if __name__ == "__main__":
    main()
