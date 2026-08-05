# Novel Translate Mobile 📖🚀

**Novel Translate Mobile** là bộ công cụ tối ưu để cào truyện chữ Trung Quốc, dịch sang tiếng Việt chất lượng cao và tự động đóng gói thành file EPUB. Dự án hỗ trợ cả hai phương thức dịch: trực tuyến qua **DeepSeek API** (tối ưu cho di động) và ngoại tuyến qua mô hình **MarianMT Local** (tối ưu cho PC).

---

## ✨ Các Chức Năng Nổi Bật

### 1. Dịch Trực Tuyến qua DeepSeek API (Khuyên dùng)
*   **Web GUI Hiện Đại:** Giao diện tối giản, responsive tốt trên trình duyệt điện thoại (chạy thông qua Termux) và máy tính.
*   **Tự Động Cào & Dịch:** Nhập URL chương đầu tiên, hệ thống sẽ tự động cào và dịch nối tiếp các chương tiếp theo.
*   **Đồng Bộ Văn Phong (Style Guide):** Tự động phân tích văn phong của chương đầu tiên (phong cách, từ xưng hô, thể loại) để định hướng dịch nhất quán cho toàn bộ các chương sau.
*   **Từ Điển Thuật Ngữ (Glossary):** Đảm bảo dịch đồng bộ tên nhân vật/thuật ngữ. Tự động phát hiện tên mới (`new_names`), cập nhật ngược lại vào file `glossary.json` để sử dụng ở các chương tiếp theo.
*   **Đóng Gói EPUB:** Tự động tạo file sách điện tử `.epub` hoàn chỉnh có đầy đủ mục lục và định dạng đẹp sau khi hoàn thành.
*   **Tự Động Tiếp Tục (Resume):** Nếu quá trình dịch bị gián đoạn, bạn chỉ cần chạy lại lệnh, hệ thống sẽ tự động bỏ qua các chương đã cào và dịch xong.

### 2. Dịch Ngoại Tuyến qua MarianMT (Offline)
*   **Mô Hình Tinh Chỉnh (Fine-tuned):** Sử dụng mô hình MarianMT (~50M parameters) tinh chỉnh trên **10GB** dữ liệu song ngữ Trung-Việt chất lượng cao.
*   **ONNX Runtime:** Được tối ưu hóa cho ONNX Runtime giúp tăng tốc độ suy luận (inference) và tiết kiệm tài nguyên. Phù hợp chạy ngoại tuyến hoàn toàn trên PC hoặc môi trường hỗ trợ tốt ONNX.
*   **Giao Diện Desktop:** Hỗ trợ giao diện Tkinter trên PC (`novel_gui.py`) hoặc chạy local server (`app.py`).

---

## 📱 Hướng dẫn Cài đặt & Cập nhật trên Termux (Android)

### 1. Cài đặt mới (Chạy 1 dòng duy nhất)
Mở ứng dụng Termux và sao chép/dán lệnh sau để tự động cài đặt mọi thư viện và cấu hình khởi chạy:
```bash
curl -sOL https://raw.githubusercontent.com/quockhanh3878/novel-translate-mobile/main/setup_termux.sh && bash setup_termux.sh
```

### 2. Cập nhật bản mới nhất
Nếu bạn đã cài đặt bản cũ (mặc định tại thư mục `~/novel`), chạy lệnh sau để cập nhật mã nguồn mới nhất:
```bash
cd ~/novel && git pull && pip install -r requirements.txt
```
> [!IMPORTANT]
> Sau khi chạy lệnh cập nhật xong, hãy **tắt hoàn toàn Termux** (chọn `Exit` từ thanh thông báo vuốt xuống hoặc gõ lệnh `exit`) rồi mở lại Termux để kích hoạt Web GUI chạy bản mới nhất.

### 3. Khởi chạy thủ công
Thông thường ứng dụng sẽ tự động khởi động khi bạn mở Termux. Nếu muốn chạy thủ công, hãy sử dụng:
```bash
cd ~/novel && python web_gui.py
```
Sau đó mở trình duyệt điện thoại truy cập: `http://localhost:8000`

---

## 💻 Hướng dẫn Chạy trên Máy Tính (PC)

### Cách 1: Chạy Web GUI Dịch DeepSeek (Online)
1.  **Tải mã nguồn:**
    ```bash
    git clone https://github.com/quockhanh3878/novel-translate-mobile.git
    cd novel-translate-mobile
    ```
2.  **Cài đặt thư viện:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Cấu hình API Key:**
    Tạo file `.env` ở thư mục gốc của dự án với nội dung:
    ```env
    DEEPSEEK_API_KEY=sk-xxxxxx_cua_ban_o_day
    ```
4.  **Khởi chạy:**
    ```bash
    python web_gui.py
    ```
    Mở trình duyệt truy cập: `http://localhost:8000`

### Cách 2: Chạy Dịch Offline qua MarianMT (Local)
1.  **Cài đặt các thư viện bổ sung:**
    ```bash
    pip install numpy onnxruntime pillow ebooklib requests beautifulsoup4
    ```
2.  **Tải Model ONNX:**
    Tải các file mô hình MarianMT ONNX (gồm `encoder_model.onnx`, `decoder_model.onnx`, `tokenizer.json`, `config.json` và thư mục `cat_dong/` nếu có) và đặt vào thư mục `model/` ở thư mục gốc của dự án.
3.  **Khởi chạy GUI Desktop:**
    ```bash
    python novel_gui.py
    ```
    Hoặc khởi động backend server dịch máy:
    ```bash
    python app.py
    ```

---

## 📂 Cấu Trúc Các File Chính

*   `web_gui.py`: Giao diện Web GUI chính chạy trên thiết bị di động (Termux) và PC (chế độ dịch DeepSeek).
*   `pipeline.py`: Script kết nối các bước: Cào truyện -> Dịch DeepSeek API -> Đóng gói EPUB.
*   `crawler.py`: Module cào nội dung truyện tự động từ link chương.
*   `deepseek_translate.py`: Module xử lý dịch thuật bằng DeepSeek API kết hợp glossary & style guide.
*   `build_epub.py`: Module đóng gói file text dịch thành sách điện tử `.epub`.
*   `glossary.json`: File lưu trữ từ điển tên nhân vật, địa danh và thuật ngữ.
*   `novel_gui.py` & `app.py`: Giao diện và API server dành cho chế độ dịch offline MarianMT cục bộ.

---

## 📝 Ví Dụ Bản Dịch (MarianMT)

**Tiếng Trung:**
```text
师尊终于出关了。
```
**Tiếng Việt:**
```text
Sư tôn cuối cùng cũng xuất quan.
```

**Tiếng Trung:**
```text
道友，请留步。
```
**Tiếng Việt:**
```text
Đạo hữu, xin hãy dừng bước.
```

---

## 📄 License

Dự án này chứa mã nguồn tinh chỉnh mô hình và các công cụ hỗ trợ liên quan. Vui lòng tôn trọng giấy phép sử dụng của mô hình gốc MarianMT cũng như bất kỳ bộ dữ liệu nào được sử dụng trong quá trình huấn luyện.

## 👤 Tác Giả

Phi Tran
