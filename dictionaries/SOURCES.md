# Hán Việt Dictionary Sources

Tài liệu này mô tả các nguồn dữ liệu đã sử dụng để xây dựng bộ từ điển Hán Việt
cho dự án `novel-translate-mobile`.

## Kết quả cuối cùng

| File | Số entries | Mô tả |
|------|----------:|-------|
| `dictionaries/hanviet_words.json` | **205,808** | Cụm từ Hán → nghĩa Việt |
| `dictionaries/hanviet_chars.json` | **13,192** | Chữ Hán → danh sách âm Hán Việt |
| `glossary.json` | **205,808** | MERGED với entries user (giữ user entries ưu tiên) |

**Coverage:** 97.1% trên 200+ test cases (chữ Hán thường gặp, từ Tu Chân, tên nhân vật lịch sử).
Chỉ 6 entries missing đều là tên riêng light novel cụ thể (陆渊, 苏沐雨, 林动, 萧炎, 牧尘, 林枫) — user tự thêm vào `glossary.json`.

## Nguồn dữ liệu (đã clone về `C:/Users/quock/AppData/Local/Temp/opencode/dict-sources/`)

### 1. CVDICT (ph0ngp/CVDICT) - ⭐ Nguồn chính
- **URL**: https://github.com/ph0ngp/CVDICT
- **License**: CC BY-SA 4.0
- **Quy mô**: 122,591 entries (words + phrases)
- **Format**: `.u8` plain text (CEDICT variant)
- **Cung cấp**: 120,180 words đã thêm
- **Tại sao chọn**: Dữ liệu Hán-Việt lớn nhất open-source, đã dịch bằng GPT-4o + review thủ công.

### 2. hanviet-pinyin-wordlist (ph0ngp)
- **URL**: https://github.com/ph0ngp/hanviet-pinyin-wordlist
- **License**: MIT
- **Quy mô**: ~10,500 chữ Hán (multi-reading)
- **Format**: CSV `char,hanviet,pinyin`
- **Cung cấp**: 10,526 chars, 11,260 readings
- **Tại sao chọn**: Cột `hanviet` riêng biệt + pinyin, xử lý multi-reading (中=trung/trúng).

### 3. chinese-hanviet-cognates (ryanphung) - ⭐ Bonus data lớn
- **URL**: https://github.com/ryanphung/chinese-hanviet-cognates
- **License**: CC (cần verify)
- **Quy mô**: 5,018 cognates đã verify + bonus files
- **Format**: TSV + text files
- **Cung cấp**:
  - `outputs/chinese-hanviet-cognates.tsv`: 5,018 từ phổ biến có freq ranking
  - `inputs/phienam.txt`: 11,411 chữ Hán đơn lẻ với âm Hán Việt
  - `inputs/vietphrases.txt`: **107,303 cụm từ** Hán-Việt (thành ngữ, idiom, câu văn)
- **Tại sao chọn**: `vietphrases.txt` chứa các câu thành ngữ dài mà CVDICT thiếu (vd: "以其人之道，还治其人之身").

### 4. chugiai-zh-en-vi (thaoshibe) - JSON format
- **URL**: https://github.com/thaoshibe/chugiai-zh-en-vi
- **License**: CC BY-SA 4.0 (data)
- **Quy mô**: 119,003 entries (CVDICT dạng JSON) + 120,589 (CC-CEDICT Anh)
- **Format**: JSON `cvdict_full.json`, `cedict_full.json`
- **Cung cấp**: 0 (vì chồng lấn với CVDICT.u8 — đã được cover trước)
- **Tại sao chọn**: Format JSON sẵn (fallback nếu CVDICT.u8 lỗi), có thêm CC-CEDICT Anh để cross-reference.

### 5. hanzi-sino-vietnamese (binhbuithithanh) - HSK chars
- **URL**: https://github.com/binhbuithithanh/hanzi-sino-vietnamese
- **License**: CC BY 4.0
- **Quy mô**: 768 chữ (HSK 1-6 + extras) với mnemonic
- **Format**: JSON `data/characters.json`
- **Cung cấp**: 768 chars với sinoViet readings
- **Tại sao chọn**: Chất lượng cao, kèm mnemonic + pinyin + nghĩa Việt.

### 6. rongmotamhon.net (Liên Phật Hội) - Crawled (optional)
- **URL**: https://rongmotamhon.net/tu-dien_han-viet_none_rong-mo-tam-hon.html
- **License**: Vui lòng ghi rõ xuất xứ khi sử dụng (theo site policy)
- **Quy mô**: 55,624 mục từ
- **Format**: HTML form-based search (submit POST `tra_van` với âm Hán Việt)
- **Cung cấp**: 784 entries đã crawl (cache trong `dictionaries/rongmotamhon_raw.json`)
- **Cơ chế crawl**:
  1. POST form `tra_van=<syllable>` → trả về list entries theo âm
  2. Mỗi entry URL dạng `tu-dien_han-viet_<slug>_rong-mo-tam-hon.html`
  3. Parse breadcrumb JSON-LD để lấy chữ Hán, parse `<p class="lead">` để lấy nghĩa Việt
- **Lưu ý**: Site có rate-limit (HTTP 429), cần delay >= 1s/req. Full crawl 55K ~24h.
- **Tại sao chọn**: Nguồn Việt thuần từ các Từ điển Trần Văn Chánh, Nguyễn Quốc Hùng, Thiều Chửu.

### 7. Seed terms thủ công (dictionaries/xianxia_terms.py)
- **License**: MIT (project-internal)
- **Quy mô**: 308 entries
- **Phân loại**:
  - **XIANXIA_TERMS**: 200+ thuật ngữ Tu Chân/Tiên Hiệp (cảnh giới, công pháp, pháp bảo...)
  - **URBAN_TERMS**: 60+ thuật ngữ Đô Thị/Hiện đại (chức vụ công ty, y tế, cảnh sát...)
  - **WUXIA_TERMS**: 50+ thuật ngữ Võ Hiệp (nội công, kinh mạch, võ công...)
  - **HISTORICAL_FIGURES**: 60+ nhân vật lịch sử Trung Quốc nổi tiếng (Tần Thủy Hoàng, Lý Bạch, Tôn Ngộ Không...)

## Cấu trúc thư mục

```
novel-translate-mobile/
├── dictionaries/
│   ├── hanviet_chars.json         # 13K chữ Hán → readings (list)
│   ├── hanviet_words.json         # 205K cụm từ → nghĩa
│   ├── rongmotamhon_raw.json      # Cache crawl (784 entries)
│   └── xianxia_terms.py           # Seed terms thủ công (308 entries)
├── scripts/
│   ├── build_hanviet_dict.py      # Script chính: build từ 6 nguồn
│   ├── crawl_rongmotamhon.py      # Crawler rongmotamhon.net
│   ├── test_verify_dict.py        # Verify chất lượng
│   └── debug_dict_formats.py      # Debug format data
├── glossary.json                  # MERGED - dùng cho translation pipeline
└── glossary.json.bak.*            # Backup tự động trước mỗi lần build
```

## Cách sử dụng

### Build lại từ đầu

```bash
# 1. Clone các nguồn (chỉ cần làm 1 lần)
mkdir -p C:\Users\quock\AppData\Local\Temp\opencode\dict-sources
cd C:\Users\quock\AppData\Local\Temp\opencode\dict-sources
git clone --depth 1 https://github.com/ph0ngp/CVDICT.git
git clone --depth 1 https://github.com/ph0ngp/hanviet-pinyin-wordlist.git
git clone --depth 1 https://github.com/ryanphung/chinese-hanviet-cognates.git
git clone --depth 1 https://github.com/thaoshibe/chugiai-zh-en-vi.git
git clone --depth 1 https://github.com/binhbuithithanh/hanzi-sino-vietnamese.git

# 2. (Optional) Crawl rongmotamhon.net
python scripts/crawl_rongmotamhon.py --delay 1.5 --output dictionaries/rongmotamhon_raw.json

# 3. Build dictionaries + merge vào glossary.json
python scripts/build_hanviet_dict.py

# 4. Verify
python scripts/test_verify_dict.py
```

### Tích hợp với pipeline dịch

`glossary.json` đã được merge sẵn với format `{chữ Hán: nghĩa Việt}` — tương thích 100% với `deepseek_translate.py` hiện tại.

Hệ thống đã hỗ trợ:
- **Sliding window**: chỉ gửi ~50 thuật ngữ quan trọng nhất (dựa trên tần suất + last-seen)
- **TTL Cleanup**: tự động xóa terms `count=1` và vắng bóng >100 chương

Với 205K entries, hệ thống tự động lọc thông minh giúp:
- Không phình file glossary
- Context window không bị tràn
- DeepSeek context cache hit rate vẫn cao

## License & Attribution

- **CVDICT**: CC BY-SA 4.0 — giữ credit Phong Phan khi phân phối
- **hanviet-pinyin-wordlist**: MIT
- **chinese-hanviet-cognates**: CC (verify trước khi thương mại hoá)
- **chugiai-zh-en-vi**: CC BY-SA 4.0
- **hanzi-sino-vietnamese**: CC BY 4.0
- **rongmotamhon.net**: Ghi rõ nguồn "rongmotamhon.net - Liên Phật Hội" khi sử dụng
- **Seed terms (xianxia_terms.py)**: MIT (project-internal)

Tất cả data được merge vào `glossary.json` vẫn giữ nguyên license gốc từng entry.