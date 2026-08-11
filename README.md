# DeepSeek Novel Translator & EPUB Packager

Bộ công cụ cào truyện Trung Quốc, dịch thuật chất lượng cao qua DeepSeek API và tự động đóng gói thành file EPUB hoàn chỉnh. Dự án được thiết kế tối ưu cho thiết bị di động (chạy trên Android qua Termux) và máy tính cá nhân (PC).

---

## 🌟 Các chức năng chính

* 🕷️ **Cào truyện thông minh**: Tự động lấy nội dung từ URL chương nguồn. Tích hợp thời gian chờ lịch sự (delay 1-5 giây) giúp tránh bị máy chủ chặn IP (Anti-scraping bypass).
* 🤖 **Dịch thuật AI chất lượng cao**: Kết nối trực tiếp tới API DeepSeek (`deepseek-v4-flash`, `deepseek-chat`,...) với Prompt được tinh chỉnh tối ưu cho dịch thuật văn học Trung-Việt.
* 📖 **Đồng bộ Thuật ngữ thông minh (Smart Glossary + Sliding Window)**: Tự động phân tích thể loại truyện (Tiên hiệp, Đô thị...) để trích xuất **đúng các danh mục từ vựng đặc thù** (công pháp, cảnh giới, tên công ty, v.v.). Hệ thống theo dõi tần suất và thời gian gần nhất của mỗi thuật ngữ, chỉ gửi ~50 thuật ngữ quan trọng nhất vào context window. File `glossary_meta.json` được tự động **làm sạch (TTL Cleanup)** định kỳ sau mỗi batch — các thuật ngữ `count=1` và vắng bóng quá 100 chương sẽ bị xóa để tránh phình file.
* ✍️ **Đồng bộ Văn phong định kỳ (Style Re-analyze)**: Tự động phân tích văn phong từ 5 chương trải đều đầu/giữa/cuối khi bắt đầu. Đối với truyện dài 1000+ chương, **tự động tái phân tích lại sau mỗi 200 chương** để bắt kịp sự thay đổi văn phong giữa các arc truyện.
* 🛡️ **Xử lý lỗi API bền bỉ (Robust Error Handling)**:
  * **Exponential Backoff**: Tự động retry với thời gian chờ tăng dần (2s, 4s, 8s...) khi gặp Rate Limit (429) hoặc Timeout (504).
  * **JSON Fallback**: Nếu API trả về JSON lỗi cú pháp, hệ thống tự động dùng Regex bóc tách nội dung dịch thay vì crash pipeline.
  * **Hết số dư tài khoản (Balance Detection)**: Tự động nhận biết HTTP 402 `insufficient_user_balance` — dừng ngay lập tức, **không retry vô ích**, in thông báo rõ ràng và bảo toàn tiến độ để Resume khi nạp tiền xong.
* 📚 **Đóng gói EPUB chuyên nghiệp**: Tự động chuyển đổi định dạng, làm sạch văn bản và xuất ra file `.epub` có mục lục hoàn chỉnh.
* ✅ **Kiểm tra chất lượng tự động (Validation)**: Module `validator.py` tự động chạy sau khi dịch xong để phát hiện: chương bị rỗng, số chương bị lệch so với bản gốc, và tồn dư ký tự tiếng Hán chưa được dịch.
* 🔀 **Dịch nhiều truyện song song (Multi-Novel)**: `multi_pipeline.py` cho phép dịch nhiều bộ truyện cùng lúc từ một file cấu hình JSON. Các luồng chia sẻ tín hiệu dừng chung — nếu một truyện gặp lỗi hết token, **tất cả đều dừng ngay lập tức**.
* ⏯️ **Tự động tiếp tục (Resume)**: Mỗi truyện ghi đĩa sau mỗi chương. Khi bị gián đoạn, chạy lại sẽ tự động bỏ qua các chương đã dịch thành công.
* 💰 **Tối ưu chi phí (Peak Hour Detect)**: Tự động nhận diện khung giờ cao điểm (9-12h, 14-18h giờ Bắc Kinh, giá tăng gấp đôi) để tạm dừng và tự động tiếp tục.
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
cd ~/novel && git fetch origin && git reset --hard origin/main && pip install -r requirements.txt
```
*Sau khi cập nhật:* Tắt hoàn toàn Termux rồi mở lại để khởi động lại Web GUI.

### 3. Khởi chạy thủ công
```bash
cd ~/novel && python web_gui.py
```
Sau đó truy cập: [http://localhost:8000](http://localhost:8000)

### 4. Quản lý tiến trình & Lấy file khi bị ngắt giữa chừng
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

### 5. Khắc phục lỗi Termux bị đóng đột ngột (Killed in background)
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
python web_gui.py
```
Mở trình duyệt: [http://localhost:8000](http://localhost:8000)

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
| `--model` | `deepseek-v4-flash` | Model dịch thuật |
| `--workers` | `1` | Số luồng dịch song song (>1 có thể làm mất nhất quán tên riêng) |
| `--temperature` | `1.3` | Độ sáng tạo khi dịch |
| `--chapters` | `0` | Giới hạn số chương cần cào/dịch (0 = toàn bộ) |
| `--stream` | — | **[MỚI]** Kích hoạt chế độ Stream: cào xong chương nào, dịch ngay chương đó |
| `--no-style-detect` | — | Bỏ qua nhận diện văn phong |
| `--allow-peak` | — | Cho phép dịch trong giờ cao điểm |

#### Cách 4: Stream Mode — Cào và Dịch Đồng Thời 🆕
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

#### Cách 3: Multi-Novel Pipeline (Nhiều truyện song song) 🆕
Dịch nhiều bộ truyện cùng lúc từ một file cấu hình JSON:

**Bước 1:** Tạo file `novels.json` (xem mẫu tại `novels.example.json`):
```json
[
  {
    "raw": "truyen_A_raw.txt",
    "title": "Tên Truyện A",
    "author": "Tác Giả A",
    "glossary": "glossary_A.json"
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

## ⚙️ Cấu hình nâng cao

### Cấu hình Glossary (Từ điển thuật ngữ)
File `glossary.json` là object JSON phẳng `"Trung": "Việt"`:
```json
{
  "陆渊": "Lục Uyên",
  "苏沐雨": "Tô Mộc Vũ",
  "荒古圣体": "Hoang Cổ Thánh Thể"
}
```
Hệ thống tự cập nhật file này khi phát hiện tên riêng mới trong quá trình dịch.

### Glossary Sliding Window & TTL Cleanup
File `glossary_meta.json` (tự sinh) theo dõi tần suất:
```json
{
  "陆渊": {"last_seen": 42, "count": 15},
  "苏沐雨": {"last_seen": 38, "count": 12},
  "路人甲": {"last_seen": 5, "count": 1}
}
```
Hệ thống chỉ gửi ~50 thuật ngữ quan trọng nhất vào prompt (tiết kiệm 500-7500 tokens/chương). Các thuật ngữ lỗi thời (`count=1`, vắng bóng >100 chương) được **tự động xóa** để tránh phình file.

---

## 📂 Cấu trúc mã nguồn

| File | Chức năng |
|---|---|
| [web_gui.py](web_gui.py) | Giao diện Web GUI (chọn file, dịch thử, nút Dừng) |
| [pipeline.py](pipeline.py) | Pipeline đơn: Cào → Dịch → Validate → EPUB |
| [multi_pipeline.py](multi_pipeline.py) | 🆕 Pipeline đa truyện song song với balance detection |
| [crawler.py](crawler.py) | Module cào dữ liệu từ web |
| [deepseek_translate.py](deepseek_translate.py) | Module dịch thuật (Glossary, Style Guide, Error Handling, Balance Detection) |
| [validator.py](validator.py) | 🆕 Module kiểm tra chất lượng bản dịch (sanity check) |
| [build_epub.py](build_epub.py) | Module đóng gói EPUB |
| [text_postprocess.py](text_postprocess.py) | Module hậu xử lý, chuẩn hóa chính tả tiếng Việt |
| [novels.example.json](novels.example.json) | 🆕 File cấu hình mẫu cho multi_pipeline.py |
| [setup_termux.sh](setup_termux.sh) | Kịch bản cài đặt tự động trên Termux |
| [run_termux.sh](run_termux.sh) | Kịch bản khởi chạy nhanh / Widget Android |

---

## 📄 Giấy phép
Dự án được phân phối dưới giấy phép MIT License. Xem chi tiết tại file [LICENSE](LICENSE).
