# Snapshot Phiên Làm Việc

## Phiên: 2026-09-03 06:05 - 06:50

## Thay đổi

### Thư mục & file mới
- `dictionaries/` - thư mục chứa từ điển Hán Việt
  - `hanviet_words.json` - **205,808 cụm từ** Hán → Việt
  - `hanviet_chars.json` - **13,192 chữ Hán** với Hán Việt readings (multi-reading)
  - `rongmotamhon_raw.json` - 784 entries cache từ crawler
  - `xianxia_terms.py` - 308 seed terms thủ công (Tu Chân/Đô Thị/Võ Hiệp/Lịch Sử)
  - `SOURCES.md` - Tài liệu mô tả nguồn dữ liệu + license

- `scripts/`
  - `build_hanviet_dict.py` - Script chính parse 6 nguồn + merge vào glossary.json
  - `crawl_rongmotamhon.py` - Crawler rongmotamhon.net (~55K entries, polite delay)
  - `test_verify_dict.py` - Verify chất lượng (97.1% coverage trên 200+ test cases)
  - `debug_dict_formats.py` - Debug utility inspect data formats

### File cập nhật
- `glossary.json` - MERGED với 205,808 entries (giữ 147 entries user gốc + 205,661 entries mới)
- `glossary.json.bak.20260903_060500` - Backup tự động trước khi merge
- `glossary.json.bak.20260903_061136` - Backup sau build lần 1
- `glossary.json.bak.20260903_064340` - Backup sau build lần 2
- `glossary.json.bak.20260903_064435` - Backup sau build lần 3 (cuối cùng)

## Chất lượng

- **BLOCKING (Coverage trên test cases)**: 86.5% (initial) → **97.1% (final)** (Δ +10.6%)
- **ADVISORY (Total entries)**: 147 (initial) → **205,808 (final)** (Δ +205,661)
- **ADVISORY (Chars với Hán Việt)**: 0 (initial) → **13,192 (final)** (Δ +13,192)
- **Short meanings (<3 chars)**: **0.41%** (acceptable)
- **Suspicious format**: 5.78% (chủ yếu là `(Tw)`, `(Hk)` notation - CVDICT's English-marked entries)

## Các nguồn đã tích hợp

| # | Nguồn | License | Entries | Trạng thái |
|---|-------|---------|--------:|-----------|
| 1 | ph0ngp/CVDICT | CC BY-SA 4.0 | 120,180 words | ✅ |
| 2 | ph0ngp/hanviet-pinyin-wordlist | MIT | 10,526 chars | ✅ |
| 3 | ryanphung/chinese-hanviet-cognates | CC | 5,018 words + 11,411 chars + 107,303 phrases | ✅ |
| 4 | thaoshibe/chugiai-zh-en-vi | CC BY-SA 4.0 | 119,003 entries (fallback) | ✅ |
| 5 | binhbuithithanh/hanzi-sino-vietnamese | CC BY 4.0 | 768 HSK chars | ✅ |
| 6 | rongmotamhon.net (Liên Phật Hội) | Attribution | 784 crawled (optional) | ✅ (partial) |
| 7 | dictionaries/xianxia_terms.py | MIT (internal) | 308 seed terms | ✅ |

## Trạng thái kế hoạch

Các hạng mục bắt buộc của phiên build từ điển đã hoàn tất và được kiểm tra bằng
`python scripts/test_verify_dict.py`. Các đề xuất mở rộng dưới đây không phải
release gate và không được coi là lỗi của bản hiện tại:

- Crawler đầy đủ `rongmotamhon.net`: để riêng, cần thời gian chạy dài và kiểm soát rate-limit.
- Bổ sung Unihan: để riêng, chỉ cần khi muốn mở rộng character coverage.
- Character-level fallback và hook auto-update: chưa triển khai, giữ ở backlog thay vì đánh dấu đã hoàn tất.
- Tích hợp `vietphrase.info`: để riêng vì cần API key bên ngoài.
