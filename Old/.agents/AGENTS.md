# Kỹ thuật cào dữ liệu (Scraping) học hỏi từ dự án Translate_with_QwenAIchat

## 1. Tách biệt quy trình (Multi-step process)
Dự án chia làm 2 bước độc lập:
- **Bước 1:** Lấy danh sách link chương (Chapter URLs) trước.
- **Bước 2:** Tải nội dung văn bản (Fetch content).
*Lợi ích:* Giúp dễ quản lý lỗi và có thể cào song song (parallel fetch) để tối ưu hiệu suất.

## 2. Xử lý chống chặn (Anti-scraping bypass)
- Cào ở chế độ không giao diện (headless browser).
- Kết hợp thêm thời gian chờ (delay 2-5 giây) giữa các chương để tránh bị máy chủ phát hiện và chặn IP.

## 3. Làm sạch văn bản sau cào (Clean remnants)
- Loại bỏ toàn bộ quảng cáo, các thẻ thừa và xử lý hậu kỳ để chuẩn hóa văn bản trước khi đưa vào dịch.
