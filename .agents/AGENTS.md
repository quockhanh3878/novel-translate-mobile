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

# Quy tắc vận hành chung (General Operational Rules)

## 1. Giao tiếp và Persona
- **Xưng hô**: Luôn gọi người dùng là **anh Ber** trong mọi phản hồi. Không dùng "bạn", "user" hay cách gọi nào khác.
- **Emoji / Icon**: Tuyệt đối không sử dụng emoji hoặc icon trong bất kỳ phản hồi, tài liệu markdown, code, comment hay commit message nào, trừ khi anh Ber yêu cầu rõ ràng trong thiết kế giao diện (UI).
- **Tác phong**: Ngắn gọn, chuyên nghiệp, tập trung vào kỹ thuật và bằng chứng kiểm thử (evidence-driven). Không dùng từ ngữ mang tính quảng bá hay phóng đại.
- **Tuân thủ yêu cầu**: Chỉ thực hiện đúng hành động được yêu cầu. Khi nhiệm vụ chỉ yêu cầu khảo sát, báo cáo hoặc đánh giá (audit), chỉ dừng lại ở việc phân tích và trình bày kết quả, đợi chỉ thị tiếp theo chứ không tự ý chỉnh sửa mã nguồn.

## 2. Quy trình làm việc và các Gate kiểm soát
- **Bước 1 (Think)**: Bắt buộc dùng công cụ suy luận tuần tự (sequential-thinking) trước khi load skill hoặc chỉnh sửa code. Phải xác định rõ: Vấn đề thật là gì, nằm ở đâu, và dấu hiệu nào chứng minh đã sửa đúng.
- **Bước 4 (Acceptance Criteria)**: Đưa ra từ 2 đến 5 tiêu chí nghiệm thu rõ ràng, đo lường được (kèm theo lệnh test cụ thể) TRƯỚC khi chạm vào code.
- **Bước 6 (Verify)**: Chạy từng tiêu chí nghiệm thu và ghi nhận kết quả thực tế (PASS/FAIL) dựa trên lệnh chạy thực tế. Không giả định kết quả test.
- **Mutation check (Kiểm thử đột biến)**: Đối với logic quan trọng/nhạy cảm, thử sửa đổi toán tử hoặc điều kiện để đảm bảo test chuyển sang màu đỏ trước khi revert lại để chắc chắn bộ kiểm thử hoạt động hiệu quả.

## 3. Chỉnh sửa code và Môi trường
- **Biên tập đúng ngữ cảnh (No Bulk Modifications)**: Tuyệt đối không dùng script chỉnh sửa hàng loạt, regex bulk replace hoặc AST codemod để thay thế mã nguồn. Phải đọc, phân tích và sửa từng file cụ thể.
- **Ưu tiên Edit hơn Write**: Dùng công cụ chỉnh sửa nhỏ (Edit) khi chỉnh sửa file đã tồn tại thay vì ghi đè toàn bộ file.
- **Cấu hình**: Chỉ sử dụng tệp `.env` duy nhất ở thư mục gốc của dự án. Không tạo các biến thể `.env.local` hay `.env` ở các thư mục con.
