# VibeTrade v1.1 — Engineering & Safety Guardrails

Các quy tắc bắt buộc áp dụng xuyên suốt mọi thư mục trong workspace `VibeTrading`:

## 1. Quy tắc bảo vệ mã nguồn và kiểm toán (Phase Discipline)
- Trong giai đoạn **P0 (Audit)**: Chỉ đọc (`Read-Only`), tuyệt đối không chỉnh sửa bất kỳ dòng code hiện có nào của repository gốc.
- Từ **P1–P8**: Chỉ can thiệp đúng phạm vi module đã được phân loại `ADAPT`, `REPLACE`, hoặc `REMOVE` trong `P0_AUDIT_REPORT.md`. Mọi milestone từ P1 đến P7 phải đi kèm unit test và regression test xanh trước khi chuyển phase.

## 2. Quy tắc dữ liệu và thời gian (Zero Repainting & Zero Lookahead)
- Mọi timestamp lưu trữ hoặc so sánh phải ở chuẩn **UTC** (ISO-8601 `Z` hoặc integer epoch milliseconds).
- Nến chưa đóng (`candle_close_time > current_time` hoặc cờ xác nhận đóng nến của sàn chưa bật) phải bị loại bỏ trước khi đưa vào tính indicator hoặc phát tín hiệu.
- Mọi tín hiệu phải định danh bằng khóa bất biến `symbol + timeframe + candle_timestamp` để bảo đảm tính lũy đẳng (idempotency).

## 3. Quy tắc định lượng minh bạch (No Fake AI / No Silent Fallback)
- Không gọi LLM API trả phí; không hardcode văn bản giả danh suy luận tự do không gắn số liệu.
- Thiếu dữ liệu đầu vào -> bắt buộc trả về `INCONCLUSIVE`.
- Không thỏa điều kiện kích thước lệnh tối thiểu, bước giá/khối lượng, phí, hoặc thanh khoản trên danh mục ảo `$10.0` -> bắt buộc ghi nhận `REJECTED_BY_CONSTRAINT`.

## 4. Quy tắc an toàn vận hành (Fail-Closed & Atomic State)
- Chỉ giao dịch mô phỏng (*Paper Trading*). Mọi đường dẫn đặt lệnh thật ra broker/exchange phải bị khóa cứng (`fail-closed`).
- Mọi file JSON trạng thái phải ghi tạm vào `.tmp`, xác thực schema rồi mới `os.replace()` sang đích.
