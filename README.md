# DeepSeek Novel Translator & EPUB Packager

Bộ công cụ cào truyện Trung Quốc, dịch thuật chất lượng cao qua DeepSeek API và tự động đóng gói thành file EPUB hoàn chỉnh. Dự án được thiết kế tối ưu cho thiết bị di động (chạy trên Android qua Termux) và máy tính (PC).

## Các chức năng chính

* Tự động cào truyện từ URL chương nguồn.
* Dịch thuật chất lượng cao thông qua DeepSeek API.
* Đồng bộ từ điển thuật ngữ (Glossary): Tự động trích xuất và quản lý tên riêng/thuật ngữ qua file glossary.json để đảm bảo sự nhất quán xuyên suốt bộ truyện.
* Đồng bộ văn phong (Style Guide): Tự động phân tích giọng văn chương đầu để áp dụng vào prompt hệ thống cho toàn bộ truyện.
* Đóng gói EPUB: Xuất file sách điện tử (.epub) hoàn chỉnh có mục lục đẹp mắt.
* Tự động tiếp tục (Resume): Bỏ qua các chương đã cào và đã dịch nếu quá trình bị gián đoạn.
* Giao diện Web GUI trực quan: Giao diện responsive mượt mà trên điện thoại và PC.

## Hướng dẫn cài đặt và chạy trên Termux (Android)

### Cài đặt mới

Mở ứng dụng Termux và chạy lệnh duy nhất dưới đây để tự động cài đặt và cấu hình:

```bash
curl -sOL https://raw.githubusercontent.com/quockhanh3878/novel-translate-mobile/main/setup_termux.sh && bash setup_termux.sh
```

### Cập nhật phiên bản mới

Chạy lệnh sau để cập nhật mã nguồn mới nhất từ GitHub:

```bash
cd ~/novel && git pull && pip install -r requirements.txt
```

Sau khi cập nhật, hãy tắt hoàn toàn Termux và mở lại để kích hoạt Web GUI phiên bản mới nhất.

### Khởi chạy thủ công

Nếu cần khởi chạy server thủ công trên Termux, chạy lệnh:

```bash
cd ~/novel && python web_gui.py
```

Sau đó truy cập trên trình duyệt điện thoại qua địa chỉ: http://localhost:8000

## Hướng dẫn cài đặt và chạy trên máy tính (PC)

### Cài đặt

1. Tải mã nguồn về máy tính:

```bash
git clone https://github.com/quockhanh3878/novel-translate-mobile.git
cd novel-translate-mobile
```

2. Cài đặt các thư viện cần thiết:

```bash
pip install -r requirements.txt
```

3. Cấu hình API Key:

Tạo một file có tên `.env` ở thư mục gốc của dự án và điền key DeepSeek của bạn vào:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### Khởi chạy

Chạy lệnh sau để khởi động Web GUI:

```bash
python web_gui.py
```

Sau đó mở trình duyệt và truy cập: http://localhost:8000

## Cấu trúc các file mã nguồn chính

* web_gui.py: Giao diện Web GUI chính.
* pipeline.py: Script kết nối toàn bộ quy trình (Cào -> Dịch -> Đóng gói EPUB).
* crawler.py: Module cào nội dung truyện.
* deepseek_translate.py: Module gọi API DeepSeek và xử lý dịch thuật.
* build_epub.py: Module đóng gói định dạng EPUB.
* glossary.json: File lưu trữ từ điển riêng cho bộ truyện.

## Tác giả

Phi Tran
