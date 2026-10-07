# DeepSeek Novel Translator & EPUB Packager

Bộ công cụ cào truyện Trung Quốc, dịch thuật chất lượng cao qua DeepSeek API và tự động đóng gói thành file EPUB hoàn chỉnh. Dự án được thiết kế tối ưu cho thiết bị di động (chạy trên Android qua Termux) và máy tính cá nhân (PC).

---

## 🌟 Các chức năng chính

* 🕷️ **Cào truyện thông minh**: Tự động lấy nội dung từ URL chương nguồn. Tích hợp thời gian chờ lịch sự (delay 1-5 giây) giúp tránh bị máy chủ chặn IP (Anti-scraping bypass).
* 🤖 **Dịch thuật AI chất lượng cao**: Kết nối trực tiếp tới API DeepSeek (mặc định `deepseek-flash`, suy luận mức trung bình) với Prompt được tinh chỉnh tối ưu cho dịch thuật văn học Trung-Việt.
* 📖 **Nhất quán tên riêng (Glossary riêng từng truyện)**: Mỗi truyện có `<file dịch>_glossary.json` riêng. Trước khi dịch, bước chuẩn bị quét cả truyện và chốt sẵn tên nhân vật, địa danh, tổ chức bằng suy luận cao; trong lúc dịch vẫn tự học tên còn thiếu; tên đã có không bao giờ bị ghi đè. Mỗi chương chỉ gửi những tên thật sự xuất hiện trong chương đó.
* ⚡ **Tối ưu DeepSeek Context Caching (MỚI)**: Glossary được sắp xếp ổn định và lọc theo cửa sổ trượt, chỉ gửi tối đa khoảng 50 thuật ngữ quan trọng vào prompt. Cách này giữ phần prompt dùng chung ổn định giữa các chương và giảm lượng token phải gửi; tỷ lệ cache hit thực tế phụ thuộc vào API và nội dung từng request.
* 🇻🇳 **Từ điển thành ngữ riêng cho từng truyện (MỚI)**: Thành ngữ, tục ngữ, 歇后语 được dịch sang thành ngữ thuần Việt tương đương (ưu tiên thuần Việt, rồi Hán Việt quen dùng, rồi khẩu ngữ; cấm dịch sát chữ). Cách dịch model đã dùng được ghi vào `<file dịch>_idioms.json` và dùng lại ở chương sau cho thống nhất cả truyện - không cần duyệt tay. Xem mục "Quy trình dịch".
* ✍️ **Đồng bộ Văn phong định kỳ (Style Re-analyze)**: Tự động phân tích văn phong từ 5 chương trải đều đầu/giữa/cuối khi bắt đầu. Đối với truyện dài 1000+ chương, **tự động tái phân tích lại sau mỗi 200 chương** để bắt kịp sự thay đổi văn phong giữa các arc truyện.
* 🛡️ **Xử lý lỗi & Tối ưu API bền bỉ (Robust Architecture)**:
  * **Exponential Backoff**: Tự động retry với thời gian chờ tăng dần (2s, 4s, 8s...) khi gặp Rate Limit (429) hoặc Timeout (504).
  * **JSON Fallback**: Nếu API trả về JSON lỗi cú pháp, hệ thống tự động dùng Regex bóc tách nội dung dịch thay vì crash pipeline.
  * **Hết số dư tài khoản (Balance Detection)**: Tự động nhận biết HTTP 402 `insufficient_user_balance` — dừng ngay lập tức, **không retry vô ích**, in thông báo rõ ràng và bảo toàn tiến độ để Resume khi nạp tiền xong.
  * **Streaming API & Connection Pooling (MỚI)**: Cắt giảm hàng trăm TLS handshakes dư thừa thông qua `requests.Session` và giải quyết triệt để lỗi timeout bằng cơ chế SSE Streaming cho các chương dài khi bật AI thinking.
  * **Write-Ahead Cache (MỚI)**: Cơ chế sao lưu thông minh (fallback) bảo toàn dữ liệu JSON ngay khi vừa nhận từ API, chống mất tiền oan khi ứng dụng crash.
  * **Cơ chế Bảo vệ Thiết bị (MỚI)**: Tự động kiểm tra dung lượng ổ đĩa chống tràn bộ nhớ và tích hợp tính năng Wake-lock giữ màn hình trên Termux chống Android đóng ứng dụng đột ngột.
* 📚 **Đóng gói EPUB chuyên nghiệp**: Tự động chuyển đổi định dạng, làm sạch văn bản và xuất ra file `.epub` có mục lục hoàn chỉnh.
* ✅ **Kiểm tra chất lượng tự động (Validation)**: Module `validator.py` tự động chạy sau khi dịch xong để phát hiện: chương bị rỗng, số chương bị lệch so với bản gốc, và tồn dư ký tự tiếng Hán chưa được dịch.
* 🔀 **Dịch nhiều truyện song song (Multi-Novel)**: `multi_pipeline.py` cho phép dịch nhiều bộ truyện cùng lúc từ một file cấu hình JSON. Các luồng chia sẻ tín hiệu dừng chung — nếu một truyện gặp lỗi hết token, **tất cả đều dừng ngay lập tức**.
* ⏯️ **Tự động tiếp tục (Resume)**: Mỗi truyện ghi đĩa sau mỗi chương. Khi bị gián đoạn, chạy lại sẽ tự động bỏ qua các chương đã dịch thành công.
* 💰 **Tối ưu chi phí (Peak Hour Detect)**: Tự động nhận diện khung giờ cao điểm (9-12h, 14-18h giờ Bắc Kinh, thứ 2 đến thứ 6, giá tăng gấp đôi; cuối tuần và ngày lễ Trung Quốc giá thấp cả ngày, ngày lễ lấy từ thư viện `holidays`) để tạm dừng và tự động tiếp tục.
* 🖥️ **Giao diện Web GUI & Widget 1-chạm**: Giao diện Responsive (Glassmorphism dark mode) mượt mà trên cả trình duyệt điện thoại và PC. Hỗ trợ Widget Termux trên Android.

---

## 📱 Hướng dẫn trên Android Termux

### 1. Cài đặt mới
Mở ứng dụng Termux trên Android và chạy duy nhất dòng lệnh dưới đây:
```bash
curl -sOL https://raw.githubusercontent.com/quockhanh3878/novel-translate-mobile/main/setup_termux.sh && bash setup_termux.sh
```
*Lưu ý:* Quá trình cài đặt sẽ yêu cầu bạn dán API Key DeepSeek và cấp quyền truy cập bộ nhớ (`termux-setup-storage`).

### 2. Cập nhật phiên bản mới (Update)
```bash
cd ~/novel && bash update_termux.sh
```
*(Script sẽ tự động diệt tiến trình cũ, cập nhật code và tự mở lại trình duyệt phiên bản mới nhất)*

`update_termux.sh` dùng `git fetch` và `git reset --hard origin/main`. Hãy sao lưu
các thay đổi cục bộ trước khi chạy vì các thay đổi chưa commit trong thư mục
`~/novel` sẽ bị ghi đè.

### 3. Thiết lập Termux trên điện thoại Realme

Để Realme không dừng Termux khi dịch truyện dài:

1. Vào Cài đặt > Ứng dụng > Termux > Pin và chọn Không hạn chế.
2. Bật Tự khởi động cho Termux nếu máy có mục này.
3. Khóa Termux trong màn hình ứng dụng gần đây.
4. Khi chạy chương dài, giữ Termux ở cửa sổ nổi hoặc chia đôi màn hình nếu hệ thống vẫn dừng tiến trình nền.

Tên menu có thể khác giữa các phiên bản realme UI. Sau khi cập nhật mã, mở lại
Termux hoặc chạy lại `bash update_termux.sh` để khởi động Web GUI trên bản mới.

### 4. Khởi chạy thủ công
```bash
cd ~/novel && python web_gui.py
```
Sau đó truy cập: [http://localhost:8000](http://localhost:8000)

### 5. Quản lý tiến trình & Lấy file khi bị ngắt giữa chừng
* **Tự động khôi phục (Resume):** Chỉ cần khởi động lại tác vụ — script tự nhận diện chương đã lưu và dịch tiếp.
* **Kiểm tra tiến trình chạy ẩn:**
  ```bash
  ps -ef | grep python
  tail -n 20 ~/novel/pipeline_*.log
  pkill -f python  # Tắt cưỡng bức
  ```
* **Lấy file EPUB ra điện thoại:**
  ```bash
  termux-setup-storage  # Cấp quyền (nếu chưa)
  cp ~/novel/*.epub /sdcard/Download/
  ```

### 6. Khắc phục lỗi Termux bị đóng đột ngột (Killed in background)
Khi chờ hết giờ cao điểm hoặc dịch truyện quá dài, Android có thể tự động giết Termux để tiết kiệm pin hoặc giải phóng RAM. Hãy thiết lập 3 bước sau:
1. **Tắt tối ưu pin (Bắt buộc):** Vào Cài đặt máy > Ứng dụng > Termux > Pin > Đổi thành **Không hạn chế (Unrestricted)**.
2. **Khoá ứng dụng (Lock App):** Mở giao diện đa nhiệm (Recent Apps), ấn giữ vào Termux và chọn biểu tượng Ổ khoá.
3. **Mở dạng Cửa sổ nổi (Floating Window) hoặc Chia đôi màn hình:** Giúp hệ thống ghi nhận Termux đang hiển thị, tránh bị "Phantom Process Killer" của Android 12+ dọn dẹp.

---

## 💻 Hướng dẫn trên máy tính (PC)

### 1. Cài đặt
Yêu cầu **Python 3.8+** và **Git**.

```bash
git clone https://github.com/quockhanh3878/novel-translate-mobile.git
cd novel-translate-mobile

python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\activate
# macOS / Linux:         source .venv/bin/activate

pip install -r requirements.txt
```

Ứng dụng hiện chạy qua DeepSeek API. `app.py` là entrypoint tương thích để mở
Web GUI API-only; không cần đặt model ONNX cục bộ.

Tạo file `.env` và điền API Key:
```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### 2. Cập nhật
```bash
git fetch origin && git reset --hard origin/main
pip install -r requirements.txt
```

### 3. Cách chạy

#### Cách 1: Web GUI (Trực quan)
```bash
python app.py
```
Mở trình duyệt: [http://localhost:8000](http://localhost:8000)

Có thể chạy trực tiếp `python web_gui.py` với cùng địa chỉ nếu cần bỏ qua
entrypoint tương thích `app.py`.

#### Cách 2: CLI Pipeline (1 truyện)
```bash
# Có URL:
python pipeline.py --start-url "https://example.com/chuong-1.html" --title "Tên Truyện" --author "Tác Giả"

# Đã có file thô:
python pipeline.py --raw "truyen_tho.txt" --title "Tên Truyện"
```

**Tham số CLI:**
| Tham số | Mặc định | Mô tả |
|---|---|---|
| `--model` | `deepseek-flash` | Model dịch thuật |
| `--reasoning-effort` | `medium` | Mức suy luận: `low` / `medium` / `high` / `max` (API quy `medium` về `high`) |
| `--workers` | `1` | Số luồng dịch song song (>1 có thể làm mất nhất quán tên riêng) |
| `--temperature` | `1.3` | Độ sáng tạo khi dịch |
| `--chapters` | `0` | Giới hạn số chương cần cào/dịch (0 = toàn bộ) |
| `--stream` | — | **[MỚI]** Kích hoạt chế độ Stream: cào xong chương nào, dịch ngay chương đó |
| `--no-style-detect` | — | Bỏ qua nhận diện văn phong |
| `--no-prepare` | — | Bỏ qua bước chuẩn bị (quét cả truyện lập glossary tên + cách dịch thành ngữ trước khi dịch) |
| `--allow-peak` | — | Cho phép dịch trong giờ cao điểm |
| `--no-thinking` | — | Tắt suy luận. Không khuyên dùng: rẻ hơn ~4 lần nhưng thành ngữ sai nghĩa, sót chữ Hán |
| `--env-file` | `.env` | File chứa `DEEPSEEK_API_KEY` |
| `--api-key` | — | Truyền API key trực tiếp cho một lần chạy |

#### Cách 3: Stream Mode — Cào và Dịch Đồng Thời 🆕
Thay vì cào hết toàn bộ truyện rồi mới dịch, chế độ này cào từng chương và **dịch ngay lập tức** sau khi cào xong mỗi chương. Phù hợp khi bạn chỉ muốn dịch thử một số chương đầu hoặc muốn nhận bản dịch sớm nhất có thể.

```bash
# Cào và dịch ngay 20 chương đầu từ link:
python pipeline.py \
    --start-url "https://example.com/truyen_1.html" \
    --title "Tên Truyện" \
    --stream \
    --chapters 20

# Không giới hạn (cào và dịch toàn bộ đồng thời):
python pipeline.py \
    --start-url "https://example.com/truyen_1.html" \
    --title "Tên Truyện" \
    --stream
```

**Lưu ý:**
* File `.txt` thô và file `.viet.txt` đều được ghi tăng dần sau mỗi chương, hỗ trợ **Resume** đầy đủ nếu bị ngắt giữa chừng.
* Style Guide được phân tích trước từ chương đầu rồi áp dụng cho toàn bộ phiên dịch stream.
* Stream Mode dùng cùng từ điển thành ngữ riêng của truyện như chế độ thường.

#### Cách 4: Multi-Novel Pipeline (Nhiều truyện song song) 🆕
Dịch nhiều bộ truyện cùng lúc từ một file cấu hình JSON:

**Bước 1:** Tạo file `novels.json` (xem mẫu tại `novels.example.json`):
```json
[
  {
    "raw": "truyen_A_raw.txt",
    "title": "Tên Truyện A",
    "author": "Tác Giả A",
    "reasoning_effort": "medium"
  },
  {
    "raw": "truyen_B_raw.txt",
    "title": "Tên Truyện B"
  }
]
```

**Bước 2:** Chạy:
```bash
python multi_pipeline.py --config novels.json
```

**Tính năng nổi bật:**
* Mỗi truyện chạy trong Thread riêng, log có prefix `[Tên Truyện]` để không lẫn lộn.
* Chia sẻ tín hiệu `balance_empty_event` chung — khi **bất kỳ truyện nào** gặp lỗi hết token API, **tất cả đều dừng ngay lập tức**.
* Cuối cùng in bảng tổng kết trạng thái từng truyện.
* Chạy lại lệnh cũ để **Resume** từ đúng chương bị dở, không tốn phí dịch lại.

---

## Quy trình dịch (chốt 2026-09-26)

1. **Cào** chương nguồn (`crawler.py`).
2. **Phân tích văn phong** từ vài chương đầu/giữa/cuối.
3. **Chuẩn bị** (`prepare_novel.py`, tự chạy, tắt bằng `--no-prepare`): quét toàn bộ truyện đã cào.
   * Tên riêng: code đếm các cụm chữ Hán lặp lại nhiều lần, đứng độc lập, không phải từ thông dụng hay thành ngữ, lấy vài trăm ứng viên kèm câu trích; model suy luận cao (high) lọc ra tên người, biệt danh, chức danh + họ, địa danh, tổ chức và chốt cách dịch. Ghi thêm vào `<file dịch>_glossary.json`, không ghi đè tên đã có.
   * Thành ngữ: mọi thành ngữ trong truyện chưa có cách dịch được model suy luận cao dịch sẵn theo cùng quy tắc ưu tiên, ghi vào `<file dịch>_idioms.json` (nguồn `chuan_bi`). Đây là **gợi ý**, không ép: thử nghiệm cho thấy ép dùng một cách dịch soạn sẵn làm sai chỗ ngữ cảnh khác.
   * Ghi nhớ đã xét gì vào `<file dịch>_prepare.json`: chạy lại chỉ gọi API cho tên/thành ngữ mới (VD cào thêm chương). Chế độ `--stream` bỏ qua bước này vì chưa có đủ truyện.
   * Chi phí thử (truyện 178 chương, 1 triệu chữ): khoảng $0.11 và 4-5 phút, thêm được 127 tên và 826 thành ngữ.
4. **Dịch từng chương** bằng `deepseek-flash`, bật suy luận mức trung bình. Mỗi chương gửi kèm:
   * tên riêng trong glossary riêng của truyện (`<file dịch>_glossary.json`) có mặt trong chương (bắt buộc dùng nguyên văn);
   * thành ngữ trong chương: nhóm "đã có cách dịch" (đã duyệt, tuyển tay, hoặc đã dùng ở chương trước) để dùng lại, nhóm "mới" kèm gợi ý của bước chuẩn bị hoặc nghĩa tham khảo.
5. **Học sau mỗi chương**: tên riêng mới vào `<file dịch>_glossary.json`; thành ngữ và cách dịch đã dùng thật trong bản dịch vào `<file dịch>_idioms.json` (cách dùng nhiều nhất thành cách dịch chính; mục đã duyệt không bao giờ bị đổi).
6. **Kiểm tra** (sót chữ Hán, tên dịch sai, số đoạn) rồi **đóng gói EPUB**.

Xem trước bước chuẩn bị mà không dịch: `python prepare_novel.py --raw <truyện thô> --output <file dịch>` (thêm `--no-api` để chỉ in danh sách ứng viên tên, không tốn phí). Muốn khóa cách dịch một thành ngữ: duyệt rồi chạy `python build_idiom_dictionary.py --output <file dịch> --apply-review <file kết quả>`.

Chi phí thử nghiệm (chương 20-21, giờ thấp điểm): khoảng $0.028/chương, 2.5-3 phút/chương.

## ⚙️ Cấu hình nâng cao

### Cấu hình Glossary (Từ điển thuật ngữ)
Mỗi truyện có glossary riêng đặt cạnh file dịch: `<file dịch>_glossary.json` (VD `truyen_A_raw.txt.viet_glossary.json`). Không cần tạo trước - truyện mới bắt đầu rỗng và tự học tên. Muốn định sẵn cách dịch một tên, sửa file này (hoặc truyền `--glossary <file>` để dùng file khác). File `glossary.json` ở thư mục gốc KHÔNG còn được nạp khi dịch. Định dạng là object JSON phẳng `"Trung": "Việt"`:
```json
{
  "陆渊": "Lục Uyên",
  "苏沐雨": "Tô Mộc Vũ",
  "荒古圣体": "Hoang Cổ Thánh Thể"
}
```
Glossary chỉ chứa **tên riêng** (nhân vật, địa danh, tổ chức) và bị ép dùng nguyên văn ở mọi chương. Hệ thống tự thêm tên mới model phát hiện, không bao giờ ghi đè tên đã có; mục mới phải có ít nhất 2 từ viết hoa (từ thường như "danh bạ", "giam giữ" bị bỏ để không lặp lỗi sang các chương sau).

### 📚 Từ điển Hán Việt tích hợp sẵn (MỚI)

Bộ từ điển Hán Việt từ **6 nguồn open-source** + 308 seed terms thủ công (không còn gộp vào `glossary.json`):

| File | Số entries | Mô tả |
|------|----------:|-------|
| `dictionaries/hanviet_chars.json` | 13,192 | Chữ Hán → list âm Hán Việt (multi-reading) |
| `dictionaries/hanviet_words.json` | 205,808 | Cụm từ Hán → Việt (format `{zh: vi}`) |
| `dictionaries/idioms_verified.json` | ~54,000 | Chỉ dùng để nhận diện thành ngữ trong chương |
| `dictionaries/idioms_curated.json` | ~80 | Thành ngữ tuyển tay, dùng cho mọi truyện |
| `dictionaries/rongmotamhon_raw.json` | 784 | Cache từ rongmotamhon.net (optional crawl) |
| `dictionaries/xianxia_terms.py` | 308 | Seed: Tu Chân + Đô Thị + Võ Hiệp + Lịch Sử |

**Các nguồn:**
- `ph0ngp/CVDICT` (CC BY-SA 4.0) - 120K entries - dịch Việt từ CC-CEDICT
- `ph0ngp/hanviet-pinyin-wordlist` (MIT) - 10.5K chữ Hán multi-reading
- `ryanphung/chinese-hanviet-cognates` - 5K từ phổ biến + 107K cụm từ trong `vietphrases.txt`
- `thaoshibe/chugiai-zh-en-vi` (CC BY-SA 4.0) - CVDICT dạng JSON
- `binhbuithithanh/hanzi-sino-vietnamese` (CC BY 4.0) - 768 chữ HSK
- `rongmotamhon.net` (Liên Phật Hội) - Từ điển Thiều Chửu, Trần Văn Chánh, Nguyễn Quốc Hùng

**Coverage: 97.1%** trên 200+ test cases (chữ Hán thường gặp + thuật ngữ Tu Chân + nhân vật lịch sử).

**Cập nhật/Build lại từ điển:**
```bash
# Clone các nguồn (chỉ cần làm 1 lần)
mkdir -p C:\Users\quock\AppData\Local\Temp\opencode\dict-sources
cd C:\Users\quock\AppData\Local\Temp\opencode\dict-sources
git clone --depth 1 https://github.com/ph0ngp/CVDICT.git
git clone --depth 1 https://github.com/ph0ngp/hanviet-pinyin-wordlist.git
git clone --depth 1 https://github.com/ryanphung/chinese-hanviet-cognates.git
git clone --depth 1 https://github.com/thaoshibe/chugiai-zh-en-vi.git
git clone --depth 1 https://github.com/binhbuithithanh/hanzi-sino-vietnamese.git

# Build (ghi dictionaries/, merge vào glossary.json - file này không còn dùng khi dịch)
python scripts/build_hanviet_dict.py

# Verify chất lượng
python scripts/test_verify_dict.py
```

Chi tiết license + attribution xem `dictionaries/SOURCES.md`.

### Glossary meta
File `<file dịch>_glossary_meta.json` (tự sinh) theo dõi tần suất:
```json
{
  "陆渊": {"last_seen": 42, "count": 15},
  "苏沐雨": {"last_seen": 38, "count": 12},
  "路人甲": {"last_seen": 5, "count": 1}
}
```
Mỗi chương chỉ gửi các tên có mặt trong chương (tối đa 300). Meta của tên ít dùng (`count=1`, vắng >100 chương) được dọn, nhưng tên vẫn giữ trong glossary để tên nhân vật quay lại sau nhiều chương vẫn dịch như cũ.

### Kiểm tra offline

Các lệnh sau không gọi DeepSeek API:

```bash
# Windows
.venv\Scripts\python.exe scripts/test_verify_dict.py
.venv\Scripts\python.exe test_cache_hit.py
.venv\Scripts\python.exe test_deepseek_pipeline.py
.venv\Scripts\python.exe test_filter_glossary.py
.venv\Scripts\python.exe test_stray_quote_fix.py
.venv\Scripts\python.exe test_idiom_review.py
.venv\Scripts\python.exe test_prepare_novel.py
.venv\Scripts\python.exe test_chapter_header.py
.venv\Scripts\python.exe test_peak_hours.py

# macOS/Linux: thay .venv\Scripts\python.exe bằng .venv/bin/python
```

`pytest` không phải dependency bắt buộc của project; các kiểm tra hiện có dùng
script Python và `unittest`.

---

## 📂 Cấu trúc mã nguồn

| File | Chức năng |
|---|---|
| [web_gui.py](web_gui.py) | Giao diện Web GUI (chọn file, dịch thử, nút Dừng) |
| [app.py](app.py) | Entrypoint tương thích, khởi động Web GUI API-only |
| [pipeline.py](pipeline.py) | Pipeline đơn: Cào → Dịch → Validate → EPUB |
| [multi_pipeline.py](multi_pipeline.py) | 🆕 Pipeline đa truyện song song với balance detection |
| [crawler.py](crawler.py) | Module cào dữ liệu từ web |
| [deepseek_translate.py](deepseek_translate.py) | Module dịch thuật (Glossary, Style Guide, Error Handling, Balance Detection) |
| [validator.py](validator.py) | 🆕 Module kiểm tra chất lượng bản dịch (sanity check) |
| [build_epub.py](build_epub.py) | Module đóng gói EPUB |
| [prepare_novel.py](prepare_novel.py) | Bước chuẩn bị trước khi dịch: lập glossary tên riêng + cách dịch thành ngữ cho cả truyện |
| [build_idiom_dictionary.py](build_idiom_dictionary.py) | Quét thành ngữ của truyện, dịch trước (tùy chọn), áp kết quả duyệt |
| [text_postprocess.py](text_postprocess.py) | Module hậu xử lý, chuẩn hóa chính tả tiếng Việt |
| [novels.example.json](novels.example.json) | 🆕 File cấu hình mẫu cho multi_pipeline.py |
| [setup_termux.sh](setup_termux.sh) | Kịch bản cài đặt tự động trên Termux |
| [run_termux.sh](run_termux.sh) | Kịch bản khởi chạy nhanh / Widget Android |
| [dictionaries/](dictionaries/) | 🆕 Từ điển Hán Việt tích hợp (205K từ + 13K chữ) |
| [scripts/build_hanviet_dict.py](scripts/build_hanviet_dict.py) | 🆕 Build từ điển từ 6 nguồn open-source |
| [scripts/crawl_rongmotamhon.py](scripts/crawl_rongmotamhon.py) | 🆕 Crawler từ rongmotamhon.net (optional) |
| [scripts/test_verify_dict.py](scripts/test_verify_dict.py) | 🆕 Verify chất lượng từ điển |
| [scripts/pre_translate_idioms.py](scripts/pre_translate_idioms.py) | Pre-translate thành ngữ trước khi gọi API |

---

## 📄 Giấy phép
Dự án được phân phối dưới giấy phép MIT License. Xem chi tiết tại file [LICENSE](LICENSE).

**Từ điển Hán Việt tích hợp:** kết hợp từ nhiều nguồn với license khác nhau
(CC BY-SA 4.0, MIT, CC BY 4.0). Xem chi tiết attribution tại
[dictionaries/SOURCES.md](dictionaries/SOURCES.md).
