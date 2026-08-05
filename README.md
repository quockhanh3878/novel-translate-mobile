# DeepSeek Novel Translator & EPUB Packager

Bộ công cụ cào truyện Trung Quốc, dịch thuật chất lượng cao qua DeepSeek API và tự động đóng gói thành file EPUB hoàn chỉnh. Dự án được thiết kế tối ưu cho thiết bị di động (chạy trên Android qua Termux) và máy tính cá nhân (PC).

---

## 🌟 Các chức năng chính

* 🕷️ **Cào truyện thông minh**: Tự động lấy nội dung từ URL chương nguồn. Tích hợp thời gian chờ lịch sự (delay 1-5 giây) giúp tránh bị máy chủ chặn IP (Anti-scraping bypass).
* 🤖 **Dịch thuật AI chất lượng cao**: Kết nối trực tiếp tới API DeepSeek (`deepseek-v4-flash`, `deepseek-chat`,...) với Prompt được tinh chỉnh tối ưu cho dịch thuật văn học Trung-Việt.
* 📖 **Đồng bộ Thuật ngữ (Smart Glossary)**: Tự động trích xuất và quản lý tên riêng, từ Hán Việt khó, danh từ riêng qua file `glossary.json`. Khi dịch, AI sẽ phát hiện các thuật ngữ mới và tự động cập nhật ngược lại vào từ điển để áp dụng cho các chương sau.
* ✍️ **Đồng bộ Văn phong (Dynamic Style Guide)**: Tự động phân tích chương đầu tiên để học hỏi giọng văn, phong cách viết (kiếm hiệp, ngôn tình, đô thị...) và áp dụng vào System Prompt của toàn bộ truyện.
* 📚 **Đóng gói EPUB chuyên nghiệp**: Tự động chuyển đổi định dạng, làm sạch văn bản (loại bỏ quảng cáo, rác HTML, thẻ thừa) và xuất ra file sách điện tử `.epub` có mục lục hoàn chỉnh để đọc trên điện thoại/máy đọc sách.
* ⏯️ **Tự động tiếp tục (Resume)**: Khi bị gián đoạn (mất mạng, hết pin), chạy lại quy trình sẽ tự động nhận diện và bỏ qua các chương đã cào hoặc đã dịch thành công trước đó.
* 💰 **Tối ưu chi phí (Peak Hour Detect)**: Tự động nhận diện khung giờ cao điểm của DeepSeek (9:00 - 12:00 và 14:00 - 18:00 giờ Bắc Kinh, khi giá API tăng gấp đôi) để tạm dừng dịch và tự động tiếp tục khi hết giờ, hoặc tùy chọn bỏ qua kiểm tra này.
* 🖥️ **Giao diện Web GUI & Widget 1-chạm**: Giao diện Responsive tuyệt đẹp (Glassmorphism dark mode) mượt mà trên cả trình duyệt điện thoại và PC. Hỗ trợ Widget Termux trên Android.

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
    *   `--workers`: Số luồng dịch song song (Mặc định: `1` để đảm bảo tính nhất quán của glossary).
    *   `--temperature`: Độ sáng tạo khi dịch (Mặc định: `1.3`).
    *   `--no-style-detect`: Bỏ qua bước tự động nhận diện văn phong chương 1.
    *   `--allow-peak`: Cho phép tiếp tục gọi API kể cả trong khung giờ cao điểm (giá nhân đôi).

---

## ⚙️ Cấu hình nâng cao

### Cấu hình Glossary (Từ điển thuật ngữ)
File `glossary.json` ở thư mục gốc giúp bạn định nghĩa trước các từ dịch cố định. Dưới đây là định dạng mẫu:
```json
{
  "characters": {
    "陆渊": "Lục Uyên",
    "苏沐雨": "Tô Mộc Vũ"
  },
  "terms": {
    "荒古圣体": "Hoang Cổ Thánh Thể",
    "大帝": "Đại Đế"
  }
}
```
*Hệ thống dịch thuật sẽ tự động nạp file này làm ngữ cảnh đầu vào và cập nhật thêm các nhân vật/thuật ngữ mới phát hiện được trong quá trình dịch.*

---

## 📂 Cấu trúc mã nguồn chính

*   [web_gui.py](file:///f:/Clone/novel-translate-mobile/web_gui.py): File khởi chạy giao diện Web GUI.
*   [pipeline.py](file:///f:/Clone/novel-translate-mobile/pipeline.py): Tập lệnh liên kết toàn bộ chuỗi xử lý (Cào -> Dịch -> Đóng gói).
*   [crawler.py](file:///f:/Clone/novel-translate-mobile/crawler.py): Module chịu trách nhiệm tải văn bản từ trang web nguồn.
*   [deepseek_translate.py](file:///f:/Clone/novel-translate-mobile/deepseek_translate.py): Module kết nối API DeepSeek, xử lý Glossary và Style Guide.
*   [build_epub.py](file:///f:/Clone/novel-translate-mobile/build_epub.py): Module đóng gói thành phẩm thành định dạng sách điện tử EPUB.
*   [text_postprocess.py](file:///f:/Clone/novel-translate-mobile/text_postprocess.py): Module hậu xử lý, chuẩn hóa chính tả và làm sạch văn bản tiếng Việt sau dịch.
*   [setup_termux.sh](file:///f:/Clone/novel-translate-mobile/setup_termux.sh): Kịch bản tự động thiết lập ban đầu trên Termux.
*   [run_termux.sh](file:///f:/Clone/novel-translate-mobile/run_termux.sh): Kịch bản bổ trợ khởi chạy nhanh / tích hợp Widget trên điện thoại Android.

---

## 📄 Giấy phép
Dự án được phân phối dưới giấy phép MIT License. Xem chi tiết tại file [LICENSE](file:///f:/Clone/novel-translate-mobile/LICENSE).
