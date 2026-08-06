# DeepSeek Novel Translator & EPUB Packager

Bộ công cụ cào truyện Trung Quốc, dịch thuật chất lượng cao qua DeepSeek API và tự động đóng gói thành file EPUB hoàn chỉnh. Dự án được thiết kế tối ưu cho thiết bị di động (chạy trên Android qua Termux) và máy tính cá nhân (PC).

---

## 🌟 Các chức năng chính

* 🕷️ **Cào truyện thông minh**: Tự động lấy nội dung từ URL chương nguồn. Tích hợp thời gian chờ lịch sự (delay 1-5 giây) giúp tránh bị máy chủ chặn IP (Anti-scraping bypass).
* 🤖 **Dịch thuật AI chất lượng cao**: Kết nối trực tiếp tới API DeepSeek (`deepseek-v4-flash`, `deepseek-chat`,...) với Prompt được tinh chỉnh tối ưu cho dịch thuật văn học Trung-Việt.
* 📖 **Đồng bộ Thuật ngữ thông minh (Smart Glossary + Sliding Window)**: Tự động trích xuất và quản lý tên riêng, từ Hán Việt khó, danh từ riêng qua file `glossary.json`. Hệ thống tự động theo dõi tần suất sử dụng và thời gian xuất hiện gần nhất của mỗi thuật ngữ, chỉ gửi ~50 thuật ngữ quan trọng nhất vào context window (thay vì toàn bộ 500+ entries) → tiết kiệm token, tránh gây nhiễu cho model.
* ✍️ **Đồng bộ Văn phong (Multi-Chapter Style Detection)**: Tự động phân tích ngẫu nhiên 5 chương trải đều từ đầu đến cuối truyện (mỗi chương ~30 đoạn) để tổng hợp phong cách dịch phù hợp nhất (the loại, giọng văn, mức độ trang trọng, cách xung hô). Kết quả style guide 3-6 câu được áp dụng nhất quán cho toàn bộ truyện.
* 📚 **Đóng gói EPUB chuyên nghiệp**: Tự động chuyển đổi định dạng, làm sạch văn bản (loại bỏ quảng cáo, rác HTML, thẻ thừa) và xuất ra file sách điện tử `.epub` có mục lục hoàn chỉnh để đọc trên điện thoại/máy đọc sách. Cảnh báo rõ ràng nếu EPUB thiếu chương do lỗi dịch.
* ⏯️ **Tự động tiếp tục (Resume)**: Mỗi truyện có file thô/file dịch riêng theo tên truyện, nên khi bị gián đoạn (mất mạng, hết pin, bấm Dừng), chạy lại đúng truyện đó sẽ tự động bỏ qua các chương đã cào hoặc đã dịch thành công trước đó mà không lẫn sang truyện khác.
* ⏹️ **Nút Dừng đáng tin cậy**: Bấm "Dừng" sẽ gửi tín hiệu SIGTERM → dừng ngay lập tức sau chương đang xử lý, không gửi thêm API request nào khác. Không cần chờ hết timeout hay retry.
* 🔄 **Bỏ qua chapter lỗi**: Nếu 1 chương gặp lỗi API (timeout, connection error...), hệ thống tự động bỏ qua chương đó, ghi nhận lỗi, và tiếp tục dịch các chương còn lại. Danh sách chapter lỗi được in rõ ràng khi hoàn thành.
* 📂 **Chọn file đã cào sẵn**: Ngoài nhập URL, có thể chọn thẳng 1 file `.txt` đã cào sẵn từ bộ nhớ máy (qua Web GUI) để dịch/đóng gói lại mà không cần cào lại từ đầu.
* 🧪 **Dịch thử trước khi chạy**: Dịch nhanh 1 đoạn văn mẫu và xuất EPUB thử để kiểm tra API Key/chất lượng dịch trước khi chạy cả truyện.
* 💰 **Tối ưu chi phí (Peak Hour Detect)**: Tự động nhận diện khung giờ cao điểm của DeepSeek (9:00 - 12:00 và 14:00 - 18:00 giờ Bắc Kinh, khi giá API tăng gấp đôi) để tạm dừng dịch và tự động tiếp tục khi hết giờ, hoặc tùy chọn bỏ qua kiểm tra này.
* 🖥️ **Giao diện Web GUI & Widget 1-chạm**: Giao diện Responsive tuyệt đẹp (Glassmorphism dark mode) mượt mà trên cả trình duyệt điện thoại và PC, có nút Dừng đáng tin cậy và khung báo lỗi kèm nút copy để dễ dàng report/fix. Hỗ trợ Widget Termux trên Android.

---

## 📱 Hướng dẫn trên Android Termux

### 1. Cài đặt mới
Mở ứng dụng Termux trên Android và chạy duy nhất dòng lệnh dưới đây để tự động cài đặt mọi thư viện và cấu hình môi trường:
```bash
curl -sOL https://raw.githubusercontent.com/quockhanh3878/novel-translate-mobile/main/setup_termux.sh && bash setup_termux.sh
```
*Lưu ý:* Quá trình cài đặt sẽ yêu cầu bạn dán API Key DeepSeek và cấp quyền truy cập bộ nhớ (`termux-setup-storage`) để xuất file EPUB ra thư mục `Documents` của điện thoại.

### 2. Cập nhật phiên bản mới (Update)
Để cập nhật mã nguồn mới nhất từ GitHub và cài đặt thêm các thư viện bổ sung nếu có thay đổi, hãy mở Termux và chạy lệnh:
```bash
cd ~/novel && git pull && pip install -r requirements.txt
```
*Sau khi cập nhật thành công:* Hãy tắt hoàn toàn ứng dụng Termux (chọn Force Close hoặc gõ `exit`) rồi mở lại để khởi động lại Web GUI với phiên bản mới nhất.

### 3. Khởi chạy thủ công
Nếu Web GUI không tự chạy hoặc bạn muốn chạy lại thủ công, thực hiện lệnh:
```bash
cd ~/novel && python web_gui.py
```
Sau đó truy cập qua trình duyệt điện thoại theo địa chỉ: [http://localhost:8000](http://localhost:8000)

---

## 💻 Hướng dẫn trên máy tính (PC)

### 1. Cài đặt
Yêu cầu máy tính đã cài đặt sẵn **Python 3.8+** và **Git**.

1. Tải mã nguồn về máy tính:
   ```bash
   git clone https://github.com/quockhanh3878/novel-translate-mobile.git
   cd novel-translate-mobile
   ```

2. Tạo môi trường ảo (Khuyên dùng) và cài đặt thư viện:
   ```bash
   python -m venv .venv
   
   # Kích hoạt trên Windows (PowerShell):
   .venv\Scripts\activate
   
   # Kích hoạt trên macOS / Linux:
   source .venv/bin/activate
   
   # Cài đặt thư viện:
   pip install -r requirements.txt
   ```

3. Cấu hình API Key:
   Tạo file `.env` ở thư mục gốc của dự án và điền API Key DeepSeek:
   ```env
   DEEPSEEK_API_KEY=your_deepseek_api_key_here
   ```

### 2. Cập nhật phiên bản mới (Update)
Để cập nhật mã nguồn và thư viện mới nhất trên PC, chạy chuỗi lệnh:
```bash
git pull
pip install -r requirements.txt
```

### 3. Cách chạy dự án

#### Cách 1: Sử dụng Web GUI (Trực quan)
Khởi chạy giao diện Web:
```bash
python web_gui.py
```
Mở trình duyệt bất kỳ và truy cập: [http://localhost:8000](http://localhost:8000)

#### Cách 2: Sử dụng Command Line (CLI Pipeline)
Nếu muốn chạy trực tiếp qua dòng lệnh để tùy biến tham số sâu hơn:
```bash
python pipeline.py --start-url "https://example.com/chuong-1.html" --title "Tên Truyện" --author "Tên Tác Giả"
```
*   Nếu đã có sẵn file văn bản thô đã cào trước đó, thay thế `--start-url` bằng `--raw`:
    ```bash
    python pipeline.py --raw "truyen_tho.txt" --title "Tên Truyện"
    ```
*   Các tham số CLI bổ sung có sẵn trong `pipeline.py`:
    *   `--model`: Model dịch thuật (Mặc định: `deepseek-v4-flash`).
    *   `--workers`: Số luồng dịch song song (Mặc định: `1` để đảm bảo tính nhất quán của glossary. **Lưu ý**: workers > 1 có thể làm mất nhất quán tên riêng giữa các chương dịch song song).
    *   `--temperature`: Độ sáng tạo khi dịch (Mặc định: `1.3`).
    *   `--no-style-detect`: Bỏ qua bước tự động nhận diện văn phong (nhiều chương đầu/giữa/cuối).
    *   `--allow-peak`: Cho phép tiếp tục gọi API kể cả trong khung giờ cao điểm (giá nhân đôi).

---

## ⚙️ Cấu hình nâng cao

### Cấu hình Glossary (Từ điển thuật ngữ)
File `glossary.json` ở thư mục gốc giúp bạn định nghĩa trước các từ dịch cố định. Đây là 1 object JSON phẳng dạng `"Trung": "Việt"` (không có nhóm `characters`/`terms` con), ví dụ:
```json
{
  "陆渊": "Lục Uyên",
  "苏沐雨": "Tô Mộc Vũ",
  "荒古圣体": "Hoang Cổ Thánh Thể",
  "大帝": "Đại Đế"
}
```
*Hệ thống dịch thuật sẽ tự động nạp file này làm ngữ cảnh đầu vào và cập nhật thêm các nhân vật/thuật ngữ mới phát hiện được trong quá trình dịch.*

### Glossary Sliding Window
Hệ thống tự động theo dõi tần suất sử dụng của mỗi thuật ngữ qua file `glossary_meta.json` (tự tạo):
```json
{
  "陆渊": {"last_seen": 42, "count": 15},
  "苏沐雨": {"last_seen": 38, "count": 12},
  "路人甲": {"last_seen": 5, "count": 2}
}
```
Khi dịch, chỉ gửi ~50 thuật ngữ quan trọng nhất (xuất hiện trong 50 chapter gần nhất hoặc có tần suất cao) vào prompt. Điều này giúp:
- Tiết kiệm token (500-1000 tokens thay vì 7500+)
- Tránh gây nhiễu cho model với quá nhiều thuật ngữ phụ
- Tên nhân vật chính luôn được ưu tiên (tần suất cao)

---

## 📂 Cấu trúc mã nguồn chính

*   [web_gui.py](web_gui.py): File khởi chạy giao diện Web GUI (bao gồm chọn file đã cào sẵn, dịch thử, nút Dừng, báo lỗi copy được).
*   [pipeline.py](pipeline.py): Tập lệnh liên kết toàn bộ chuỗi xử lý (Cào -> Dịch -> Đóng gói). Xử lý tín hiệu dừng (SIGTERM) để dừng gracefully.
*   [crawler.py](crawler.py): Module chịu trách nhiệm tải văn bản từ trang web nguồn.
*   [deepseek_translate.py](deepseek_translate.py): Module kết nối API DeepSeek, xử lý Glossary (sliding window), Style Guide (multi-chapter sampling), và skip chapter lỗi.
*   [build_epub.py](build_epub.py): Module đóng gói thành phẩm thành định dạng sách điện tử EPUB.
*   [text_postprocess.py](text_postprocess.py): Module hậu xử lý, chuẩn hóa chính tả và làm sạch văn bản tiếng Việt sau dịch. Bao gồm `postprocess_title()` riêng cho tên chương.
*   [setup_termux.sh](setup_termux.sh): Kịch bản tự động thiết lập ban đầu trên Termux.
*   [run_termux.sh](run_termux.sh): Kịch bản bổ trợ khởi chạy nhanh / tích hợp Widget trên điện thoại Android.

---

## 📄 Giấy phép
Dự án được phân phối dưới giấy phép MIT License. Xem chi tiết tại file [LICENSE](LICENSE).
